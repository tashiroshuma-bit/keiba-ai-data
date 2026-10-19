import copy
import datetime as dt
import itertools
import unittest
import numpy as np
from archive_completion import class_info
from official_linkage import parse_html
from features import HistoryIndex,build_features,timestamp,shrink,FEATURE_NAMES,ENRICHED_FEATURE_NAMES
from enriched_features import history_index,build_enriched,previous_contract_index
from fitted_model import HierarchicalModel,softmax
from result_odds import judge_combination_odds
from risk_replay import capital_replay,risk_report


def row(i=1,**kw):
    return dict(race_id='past',race_date='2023-01-01',horse_id='jra:h'+str(i),jockey_id='jra:j1',horse_number=str(i),
                off_timestamp='2023-01-01T10:00:00+09:00',result_available_at='2023-01-03T00:00:00+09:00',
                source_url='https://www.jra.go.jp/result',track='東京',surface='turf',distance_m=1600,finish_position=i,
                field_size=5,**kw)


def target(i=1):
    r=row(i);r.update(race_id='next',race_date='2023-01-08',off_timestamp='2023-01-08T10:00:00+09:00',race_category='graded',gate=i)
    return r


class CompletionTests(unittest.TestCase):
    def test_grade_order(self):
        for g,level in [('ＧⅠ',6),('GII',5),('GⅢ',4)]:self.assertEqual(class_info(g)[0],level)
        self.assertEqual(class_info('3歳以上2勝クラス')[0],2)
        self.assertEqual(class_info('新馬')[1],'nongraded')

    def test_cp932_extensions(self):
        raw='<meta charset="Shift_JIS"><p>髙田 GⅢ</p>'.encode('cp932')
        self.assertIn('髙田 GⅢ',parse_html(raw,'lxml').get_text())

    def test_future_and_target_results_do_not_change_features(self):
        h=row(margin_seconds=.2,corner4_position=2,last_3f_rank=1,relative_speed_z=.4,class_level=3)
        fs=build_enriched(history_index([h]),[target()])
        t=target();t.update(finish_position=18,final_win_odds=9999,win_payout_100=999999)
        future=row();future.update(race_id='future',off_timestamp='2023-02-01T10:00:00+09:00',result_available_at='2023-02-03T00:00:00+09:00')
        new=build_enriched(history_index([h,future]),[t])
        self.assertEqual(fs,new)
        self.assertEqual(len(fs[0]['values']),23)
        self.assertEqual(fs[0]['groups'],['東京/turf','class:graded'])

    def test_same_day_bias_observation_gate(self):
        h=row(corner4_position=1);h.update(result_available_at='2023-01-01T10:05:00+09:00')
        t=target(2);t.update(race_date='2023-01-01',off_timestamp='2023-01-01T11:00:00+09:00')
        self.assertEqual(build_enriched(history_index([h],False),[t])[0]['same_day_bias_samples'],1)
        h['result_available_at']='2023-01-01T11:00:00+09:00'
        self.assertEqual(build_enriched(history_index([h],False),[t])[0]['same_day_bias_samples'],0)

    def test_previous_input_contract(self):
        h=row(class_level=6,relative_speed_z=2,corner4_position=1,carried_weight=60)
        f=build_features(previous_contract_index([h]),[target()])[0]
        self.assertEqual(f['values'][11:],[0,0.0]);self.assertFalse(f['style_observed'])

    def test_nonfinisher_retained_as_risk(self):
        h=row();h.update(finish_position=None,runner_status='nonfinisher')
        f=build_enriched(history_index([h]),[target()])[0]
        self.assertEqual(f['history_starts'],1);self.assertGreater(f['values'][-1],.1)

    def test_jockey_prefix_exact_with_nonmonotonic_publication(self):
        rows=[row(i) for i in range(1,6)]
        for i,r in enumerate(rows):
            r.update(race_id='p'+str(i),off_timestamp=f'2023-01-0{i+1}T10:00:00+09:00',result_available_at=f'2023-01-{10-i:02}T00:00:00+09:00')
        idx=HistoryIndex(rows);off=timestamp('2023-01-10T10:00:00+09:00')
        for cutoff in ('2023-01-06T00:00:00+09:00','2023-01-09T00:00:00+09:00'):
            c=timestamp(cutoff)
            for rid in ('new','p1'):
                a=idx.jockey_form('jra:j1',rid,off,c)
                b=shrink(idx.prior('jockey','jra:j1',rid,off,c),lambda r:True,strength=20)
                self.assertEqual(a,b)

    def test_timestamp_microsecond_boundary(self):
        h=row();h['result_available_at']='2023-01-08T09:55:00.000001+09:00'
        self.assertEqual(build_features(HistoryIndex([h]),[target()])[0]['history_starts'],0)
        h['result_available_at']='2023-01-08T00:55:00+00:00'
        self.assertEqual(build_features(HistoryIndex([h]),[target()])[0]['history_starts'],1)

    def test_complete_combination_market_required(self):
        ps={','.join(c):.5 for c in itertools.combinations(['1','2','3'],2)}
        q=[dict(horse_numbers=k.split(','),decimal_odds=3,odds_basis='post_race_final',source_url='https://www.jra.go.jp/odds') for k in ps]
        self.assertEqual(judge_combination_odds(['1','2','3'],ps,q[:-1],'wide')['ranked'],[])
        self.assertEqual(judge_combination_odds(['1','2','3'],ps,q,'wide')['selected'],'1,2')

    def test_risk_concentration(self):
        r=risk_report([dict(fully_settled=True,stake_yen=100,payout_yen=x) for x in (0,0,10000,0)])
        self.assertEqual(r['longest_losing_streak'],2);self.assertEqual(r['return_pct_without_largest_payout'],0)

    def test_capital_never_spends_future_winnings(self):
        races=[dict(race_id=str(i),cutoff_timestamp=f'2025-01-01T10:{i:02}:00+09:00',result_available_at='2025-01-03T00:00:00+09:00',markets=[dict(fully_settled=True,stake_yen=100,payout_yen=0)]*3) for i in range(50)]
        a,decisions=capital_replay(races);races[0]['markets']=[dict(fully_settled=True,stake_yen=100,payout_yen=99999)]*3
        b,new=capital_replay(races)
        self.assertEqual(decisions,new);self.assertLessEqual(a['maximum_entry_exposure'],.1+1e-9)
        self.assertTrue(all(d['cash_before']>=d['stake_yen'] and d['stake_yen']<=.02*d['equity_before'] for d in new))

    def test_batched_optimizer_matches_direct_gradient(self):
        races=[]
        for k,n in enumerate((3,4)):
            fs=[]
            for i in range(n):
                fs.append(dict(horse_id='jra:h'+str(i),group='track',groups=['track','class:g'+str(k)],values=[(i+j+k)/13 for j in range(13)],cutoff_timestamp='2023-01-01T09:55:00+09:00'))
            races.append(dict(race_id=str(k),features=fs,winner_index=k,off_timestamp='2023-01-01T10:00:00+09:00',result_available_at='2023-01-03T00:00:00+09:00'))
        m=HierarchicalModel().fit(races,iterations=1)
        grad=np.zeros(13);groups={}
        for r in races:
            x=(np.array([f['values'] for f in r['features']])-m.mean)/m.scale
            residual=np.ones(len(x))/len(x);residual[r['winner_index']]-=1
            delta=x.T@residual/len(races);grad+=delta
            for g in r['features'][0]['groups']:groups[g]=groups.get(g,0)+delta
        np.testing.assert_allclose(m.weights,-.08*grad,atol=1e-14)
        for g,v in groups.items():np.testing.assert_allclose(m.offsets[g],-.08*v,atol=1e-14)
        loaded=HierarchicalModel.from_dict(m.to_dict());np.testing.assert_allclose(m.scores(races[0]['features']),loaded.scores(races[0]['features']))

if __name__=='__main__':unittest.main()
