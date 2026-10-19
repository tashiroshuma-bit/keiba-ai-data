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


class SourceCompletionTests(unittest.TestCase):
    def rich_fixture(self):
        from bs4 import BeautifulSoup
        html='''<table class="basic narrow-xy"><caption><div class="date_line"><div class="date">2025年5月17日 1回新潟5日</div><div class="time">14時16分</div><div class="baba">芝 良</div></div><div class="race_number"><img alt="9レース"></div><div class="race_title">4歳以上1勝クラス</div><div class="course">2,000メートル (芝)</div></caption><tbody>'''
        for i,place in enumerate(('1','2','3','中止','取消'),1):
            html+=f'''<tr><td class="place">{place}</td><td class="num">{i}</td><td class="horse"><a href="/JRADB/accessU.html?CNAME=pw01dud10202010067{i}/D3">馬{i}</a></td><td class="age">牡5</td><td class="jockey">外国騎手</td><td class="time">{'2:00.'+str(i) if i<4 else ''}</td><td class="f_time">34.{i}</td><td class="corner"><ul><li title="4コーナー">{i if i<5 else 1}</li></ul></td><td class="waku"><img alt="枠1"></td></tr>'''
        html+='</tbody></table><dl><dt>ワイド</dt><dd><div class="line"><span class="num">3 - 1</span><span class="yen">1,200円</span></div></dd></dl>'
        return BeautifulSoup(html,'lxml')

    def test_official_nonstarter_nonfinisher_and_canonical_payout(self):
        from archive_completion import parse_rich
        from test_official_linkage import URL
        meta=dict(url=URL,sha256='a'*64,observed_at='2026-10-19T10:00:00+00:00')
        rich=parse_rich(self.rich_fixture(),URL,meta)
        self.assertEqual(rich['status'],'complete');self.assertEqual(rich['active_horse_numbers'],[1,2,3,4])
        self.assertEqual(rich['runners'][3]['runner_status'],'nonfinisher')
        self.assertIsNone(rich['runners'][3]['jockey_id']);self.assertEqual(rich['payouts']['wide:1,3'],1200)
        self.assertEqual(rich['runners'][0]['going'],'良')

    def test_dead_heat_is_not_a_valid_training_field(self):
        from archive_completion import parse_rich
        from test_official_linkage import URL
        soup=self.rich_fixture();soup.select('td.place')[1].string='1'
        rich=parse_rich(soup,URL,dict(url=URL,sha256='a'*64,observed_at='2026-10-19T10:00:00+00:00'))
        self.assertEqual(rich['status'],'exceptional_or_incomplete')

    def test_pdf_repair_does_not_certify_unknown_odds(self):
        import tempfile,sqlite3,json
        from pathlib import Path
        from test_official_linkage import OfficialLinkageTests
        from enriched_features import load_archive
        with tempfile.TemporaryDirectory() as root:
            path,db=OfficialLinkageTests().db_fixture(root)
            db.execute("update annual_report_races set status='requires_review'")
            db.execute('CREATE TABLE enriched_results(race_id TEXT PRIMARY KEY,status TEXT,payload_json TEXT)')
            runners=[]
            for i in (5,6,7):
                r=row(i);r.update(race_id='202504010509',race_date='2025-05-17',horse_id='jra:h'+str(i),off_timestamp='2025-05-17T14:16:00+09:00',finish_position=i-4,runner_status='finished',field_size=3,horse_number=i)
                runners.append(r)
            rich=dict(runners=runners,active_horse_numbers=[5,6,7],source_url='https://www.jra.go.jp/result',source_sha256='b'*64,observed_at='2026-10-19T01:00:00+00:00',payouts={'win:5':200})
            db.execute('insert into enriched_results values(?,?,?)',('202504010509','complete',json.dumps(rich)));db.commit();db.close()
            history,fields,audit=load_archive(path)
            self.assertEqual(len(fields),3);self.assertTrue(all(r.get('final_win_odds') is None for r in fields));self.assertEqual(audit['repaired_pdf_races'],1)

    def test_settlement_does_not_choose_using_outcomes(self):
        from completion_validation import settlement
        rs=[row(i) for i in (1,2,3,4)]
        for r in rs:r.update(payouts={'win:4':99999,'wide:3,4':99999},win_payout_100=99999)
        a=settlement(rs,[.4,.3,.2,.1]);self.assertEqual(a['win']['horse_numbers'],['1'])
        for r in rs:r['finish_position']=5-r['finish_position']
        b=settlement(rs,[.4,.3,.2,.1]);self.assertEqual(a['win']['horse_numbers'],b['win']['horse_numbers'])
        self.assertEqual(b['win']['payout_yen'],0)
        rs[0]['finish_position']=1;rs[0]['win_payout_100']=None;rs[0]['payouts']={}
        self.assertFalse(settlement(rs,[.4,.3,.2,.1])['win']['fully_settled'])


class MarketJudgementTests(unittest.TestCase):
    def test_pure_market_can_abstain(self):
        from final_market_judgement import judge
        rs=[dict(horse_number=str(i+1),final_win_odds=o) for i,o in enumerate((2,3,4))]
        result=judge(rs,[.1,.2,.7],{'structural_weight':0})
        self.assertIsNone(result['selected_index']);self.assertFalse(result['actionable_before_off'])

    def test_market_tuning_rejects_2025_labels(self):
        from final_market_judgement import fit_judgement
        r=dict(off_timestamp='2025-01-01T10:00:00+09:00',cutoff_timestamp='2025-01-01T09:55:00+09:00')
        with self.assertRaises(ValueError):fit_judgement([r],'2023-12-31T00:00:00+09:00')

    def test_mixture_is_full_probability_simplex(self):
        from final_market_judgement import mixed_probabilities
        for w in (0,.25,1):self.assertAlmostEqual(sum(mixed_probabilities([.2,.3,.5],[2,3,4],w)),1)
        with self.assertRaises(ValueError):mixed_probabilities([.2,.3,.5],[2,3,4],-1)


class DeploymentVetoTests(unittest.TestCase):
    def test_final_odds_loss_vetoes_probability_eligibility(self):
        from completion_validation import adoption_decision
        r=dict(log_loss_delta=-.02,day_cluster_95pct_log_loss_delta=[-.05,-.001],final_odds_reference={'previous':{'post_race_value_settlement':{'return_pct':72}},'candidate':{'post_race_value_settlement':{'return_pct':17}}})
        d=adoption_decision([r,r],[2,7]);self.assertTrue(d['original_protocol_probability_eligibility']);self.assertFalse(d['promote_experimental_probability_only'])

    def test_activation_rejects_review_veto_before_writing(self):
        import tempfile,json
        from pathlib import Path
        from live_predict import activate
        with tempfile.TemporaryDirectory() as root:
            p=Path(root);(p/'model.json').write_text('{}');(p/'report.json').write_text(json.dumps({'live_model_promotion_approved':False}))
            with self.assertRaisesRegex(ValueError,'vetoed'):activate(p/'model.json',p/'report.json',p/'active')
            self.assertFalse((p/'active').exists())
