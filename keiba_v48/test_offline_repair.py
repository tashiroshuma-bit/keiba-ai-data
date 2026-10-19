import copy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
import test_official_linkage as linkage_fixture
from test_completion import row,target
from enriched_features import load_archive,history_index,build_enriched
from features import ENRICHED_FEATURE_NAMES
from pdf_payouts import decode_payouts
from market_residual import MarketResidualModel,market_log
from fitted_model import softmax

RAW='''単 勝 (cid:2) 120円 複 勝 (cid:2) 100円
馬 連 (cid:2)(cid:3) 170円 馬 単 (cid:2)(cid:3) 210円
払戻金・ 給付金 ワ イ ド (cid:2)(cid:3) 120円 (cid:2)(cid:4) 600円 (cid:4)(cid:3) 880円
3 連 複 (cid:2)(cid:4)(cid:3) 1,120円 3 連 単 (cid:2)(cid:3)(cid:4) 2,680円
単勝票数 計 440812 的中 (cid:2) 279205(1番人気)'''


class OfflineRepairTests(unittest.TestCase):
    def test_ordered_payout_anchor_and_independent_checks(self):
        p,proof=decode_payouts(RAW,{'5':1,'8':2,'6':3,'4':4},120)
        self.assertEqual(p,{'win:5':120,'trio:5,6,8':1120,'wide:5,8':120,'wide:5,6':600,'wide:6,8':880})
        self.assertEqual(proof['symbol_to_horse_number']['(cid:3)'],'8')

    def test_payout_decode_rejects_missing_pair_and_conflict(self):
        for text in (RAW.replace('(cid:4)(cid:3) 880円',''),RAW.replace('馬 単 (cid:2)(cid:3)','馬 単 (cid:3)(cid:2)')):
            with self.assertRaises(ValueError):decode_payouts(text,{'5':1,'8':2,'6':3},120)
        with self.assertRaises(ValueError):decode_payouts(RAW,{'5':1,'8':2,'6':3},130)
        with self.assertRaises(ValueError):decode_payouts(RAW,{'5':1,'8':1,'6':3},120)

    def test_unknown_horse_does_not_remove_whole_field_or_invent_official_id(self):
        with tempfile.TemporaryDirectory() as root:
            path,db=linkage_fixture.OfficialLinkageTests().db_fixture(root);db.close()
            _,old,_=load_archive(path);self.assertEqual(old,[])
            history,fields,audit=load_archive(path,allow_unlinked_fields=True)
            self.assertEqual(len(fields),3);self.assertEqual(audit['unlinked_evaluation_rows'],3)
            self.assertTrue(all(r['official_horse_id'] is None and r['horse_id'].startswith('unlinked:') for r in fields))
            idx=history_index(history)
            fs=build_enriched(idx,fields)
            self.assertTrue(all(f['history_starts']==0 for f in fs))

    def test_source_row_id_cannot_join_same_name_across_races(self):
        h=row();h['horse_id']='unlinked:race1_1'
        t=target();t['horse_id']='unlinked:race2_1'
        self.assertEqual(build_enriched(history_index([h]),[t])[0]['history_starts'],0)


class ResidualModelTests(unittest.TestCase):
    def races(self,year=2023):
        out=[]
        for k,n in enumerate((3,4)):
            fs=[dict(horse_id='jra:h'+str(i),group='東京/turf',groups=['東京/turf','class:nongraded'],values=[(i+j+k)/23 for j in range(23)],cutoff_timestamp=f'{year}-01-01T09:55:00+09:00') for i in range(n)]
            rs=[dict(horse_number=str(i+1),final_win_odds=2+i*2) for i in range(n)]
            out.append(dict(race_id=f'{year}_{k}',features=fs,rows=rs,winner_index=k,off_timestamp=f'{year}-01-01T10:00:00+09:00',result_available_at=f'{year}-01-03T00:00:00+09:00'))
        return out

    def test_market_offset_optimizer_matches_direct_gradient(self):
        races=self.races();m=MarketResidualModel().fit(races,iterations=1);grad=np.zeros(23)
        for r in races:
            x=(np.array([f['values'] for f in r['features']])-m.mean)/m.scale
            residual=softmax(market_log(r['rows']));residual[r['winner_index']]-=1;grad+=x.T@residual/len(races)
        np.testing.assert_allclose(m.weights,-.08*grad,atol=1e-14)

    def test_market_only_calibration_roundtrip_and_temporal_gate(self):
        m=MarketResidualModel().fit(self.races(),iterations=2)
        m.calibrate(self.races(2024),scales=[0],powers=[1])
        artifact=m.to_dict()
        with self.assertRaises(ValueError):MarketResidualModel.from_dict(artifact)
        loaded=MarketResidualModel.from_dict(artifact,allow_research=True)
        p=loaded.probabilities(self.races(2025)[0]);expected=np.array([1/2,1/4,1/6]);expected/=expected.sum()
        np.testing.assert_allclose(p,expected);self.assertAlmostEqual(sum(p),1)
        with self.assertRaises(ValueError):loaded.probabilities(self.races()[0])

    def test_current_odds_required_no_winning_payout_proxy(self):
        r=self.races()[0];r['rows'][1]['final_win_odds']=None
        with self.assertRaises((ValueError,TypeError)):MarketResidualModel().fit([r])


class LiveResearchIsolationTests(unittest.TestCase):
    def test_live_activation_rejects_post_race_market_artifact(self):
        from live_predict import activate
        with tempfile.TemporaryDirectory() as root:
            p=Path(root);(p/'model.json').write_text(json.dumps(dict(odds_basis='post_race_final',live_eligible=False)));(p/'report.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'cannot be activated'):activate(p/'model.json',p/'report.json',p/'live')
            self.assertFalse((p/'live').exists())


class PerformanceEvidenceTests(unittest.TestCase):
    def test_nonwinning_dead_heat_is_valid_for_unique_winner_model(self):
        from exceptional_results import competition_ranks_are_complete
        rows=[dict(runner_status='finished',finish_position=n) for n in (1,2,3,3,5)]
        self.assertTrue(competition_ranks_are_complete(rows))
        self.assertFalse(competition_ranks_are_complete([dict(runner_status='finished',finish_position=n) for n in (1,1,3)]))
        self.assertFalse(competition_ranks_are_complete([dict(runner_status='finished',finish_position=n) for n in (1,2,3,3,4)]))

    def test_time_prefix_and_same_time_marker_do_not_take_margin_as_decimal(self):
        from pdf_performance import parse_times
        rows=[dict(horse_number=i,horse_name='horse'+str(i),final_win_odds=2+i,finish_time_raw=t) for i,t in enumerate(('1:10.31','〃ク','1:10.8'),1)]
        result=parse_times(rows,3,[],'')
        self.assertEqual([r['finish_time_seconds'] for r in result],[70.3,70.3,70.8])
        self.assertAlmostEqual(result[-1]['margin_seconds'],.5)

    def test_ties_and_unknown_times_remain_quarantined(self):
        from pdf_performance import parse_times
        rows=[dict(horse_number=i,horse_name='h'+str(i),final_win_odds=2+i,finish_time_raw=t) for i,t in enumerate(('1:10.3','1:10.3','?'),1)]
        with self.assertRaises(ValueError):parse_times(rows,3,[],'')
        with self.assertRaises(ValueError):parse_times(rows,3,[],'同着')

    def test_risk_policy_cannot_tune_on_2025(self):
        from risk_policy import calibrate_policy
        with self.assertRaisesRegex(ValueError,'2024'):calibrate_policy([{'off_timestamp':'2025-01-01T00:00:00+09:00'}],[[]],{})

    def test_policy_selection_cannot_read_winning_payout(self):
        from risk_policy import policy_decision
        r=dict(rows=[dict(horse_number=str(i),final_win_odds=o,finish_position=i,win_payout_100=200) for i,o in enumerate((2,4,8),1)])
        a,_=policy_decision(r,[.2,.2,.6],1,10)
        r['rows'][0]['win_payout_100']=99999;r['rows'][1]['finish_position']=1
        b,_=policy_decision(r,[.2,.2,.6],1,10)
        self.assertEqual(a['horse_number'],b['horse_number'])


class CornerEvidenceTests(unittest.TestCase):
    def test_printed_group_midrank_and_no_intragroup_order_claim(self):
        from pdf_performance import fourth_corner
        p=fourth_corner('通過順位 3 1,2,3,4 4 1(2,3)4\n勝馬の', [1,2,3,4])
        self.assertEqual(p[2]['corner4_position'],2.5);self.assertEqual(p[2]['corner4_range'],[2,3]);self.assertEqual(p[3]['corner4_position'],2.5)
        self.assertIsNone(fourth_corner('通過順位 4 1(2,3)\n勝馬の',[1,2,3,4]))

    def test_group_straddling_front_threshold_is_unknown(self):
        from features import front_status
        self.assertIsNone(front_status(dict(field_size=10,corner4_position=4.5,corner4_range=[3,6])))
        self.assertTrue(front_status(dict(field_size=10,corner4_position=1.5,corner4_range=[1,2])))

    def test_current_result_performance_cannot_change_pre_race_features(self):
        h=row(margin_seconds=.2,corner4_position=1,relative_speed_z=.1);t=target()
        a=build_enriched(history_index([h]),[t])
        t.update(margin_seconds=0,corner4_position=18,relative_speed_z=-9)
        self.assertEqual(a,build_enriched(history_index([h]),[t]))


class CornerIntegrationTests(unittest.TestCase):
    def test_source_corner_is_attached_or_quarantined_on_conflict(self):
        from offline_performance_repair import attach_corner
        rows=[dict(horse_number=i,runner_status='finished') for i in (1,2,3,4)]
        text='通過順位 4 1(2,3)4\n勝馬の'
        attached,conflict=attach_corner(rows,text,[dict(horse_number=2,corner4_position=2)])
        self.assertTrue(attached);self.assertFalse(conflict);self.assertEqual(rows[1]['corner4_position'],2.5)
        other=[dict(horse_number=i,runner_status='finished') for i in (1,2,3,4)]
        attached,conflict=attach_corner(other,text,[dict(horse_number=2,corner4_position=4)])
        self.assertFalse(attached);self.assertTrue(conflict);self.assertNotIn('corner4_position',other[1])
