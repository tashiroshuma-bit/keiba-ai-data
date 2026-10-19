"""Synthetic boundary tests for final-odds reference and experimental activation."""
import datetime as dt
import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from annual_reports import connect
from features import HistoryIndex,build_features
from fitted_model import HierarchicalModel
from live_predict import activate,digest,forecast
from official_linkage import propagate,schema,rebuild_from_cache
from result_odds import final_market_probabilities,judge_final_odds,summarize_final_odds
from test_improvements import field,trained
import test_official_linkage as linkage_tests


class OperationalTests(unittest.TestCase):
    def test_rebuild_publishes_verified_snapshot_without_touching_original(self):
        with tempfile.TemporaryDirectory() as root:
            source,db=linkage_tests.OfficialLinkageTests().db_fixture(root)
            db.commit();db.close()
            original=hashlib.sha256(Path(source).read_bytes()).hexdigest()
            cache=Path(root)/'cache';cache.mkdir()
            dest=Path(root)/'snapshot.sqlite'
            report=rebuild_from_cache(source,dest,cache)
            self.assertEqual(report['integrity_check'],'ok')
            self.assertEqual(report['foreign_key_violations'],0)
            self.assertEqual(original,hashlib.sha256(Path(source).read_bytes()).hexdigest())
            with self.assertRaisesRegex(ValueError,'must not already exist'):
                rebuild_from_cache(source,dest,cache)

    def test_final_odds_are_explicit_postrace_and_selection_ignores_result(self):
        rows=[dict(horse_number=str(i),final_win_odds=o,finish_position=i) for i,o in [(1,2),(2,4),(3,10)]]
        p=[.5,.3,.2]
        a=judge_final_odds(rows,p)
        self.assertFalse(a['actionable_before_off'])
        self.assertEqual(a['selected_horse_number'],'3')
        b=judge_final_odds([{**r,'finish_position':99} for r in rows],p)
        self.assertEqual(a,b)
        self.assertAlmostEqual(sum(a['market_probabilities']),1)
        with self.assertRaises(ValueError):final_market_probabilities([2,float('nan'),4])
        self.assertAlmostEqual(sum(final_market_probabilities([1,10,20])),1)

    def test_missing_jockey_is_masked_without_inventing_an_identity(self):
        h=[{**r,'jockey_id':None} for r in field(2022)]
        with self.assertRaises(ValueError):HistoryIndex(h)
        index=HistoryIndex(h,allow_missing_jockey=True)
        result=build_features(index,[{**r,'jockey_id':None} for r in field()])
        self.assertTrue(all(r['jockey_id'] is None and r['jockey_identity_missing'] for r in result))
        self.assertEqual(result[0]['history_starts'],1)
        self.assertEqual(result[0]['values'][6],.25)

    def test_pdf_alias_needs_three_sources_and_rejects_mixed_initials(self):
        with tempfile.TemporaryDirectory() as root:
            _,db=linkage_tests.OfficialLinkageTests().db_fixture(root)
            db.execute("UPDATE annual_report_runners SET jockey_name='.デムーロ'")
            for n in (1,2,3):
                rid='source'+str(n)
                db.execute('''INSERT INTO annual_report_races SELECT ?,document_url,page_number,panel,race_number,race_date,track,
                    surface,distance_m,going,off_timestamp,expected_runners,status,issues_json,metadata_json
                    FROM annual_report_races WHERE race_id='202504010509' ''',(rid,))
                db.execute('''INSERT INTO annual_report_runners SELECT ?,horse_number,finish_order,'ソース馬',jockey_name,
                    horse_id,jockey_id,payload_json FROM annual_report_runners WHERE race_id='202504010509' AND horse_number=5''',(rid,))
                payload=json.dumps(dict(jockey_name='M.デムーロ'))
                db.execute('INSERT INTO official_identity_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                           (rid,5,'ソース馬',2020,'jra:2020100000','M.デムーロ','jra:005212',
                            'https://www.jra.go.jp/source','a'*64,'2026-10-19T00:00:00+00:00',payload))
            propagate(db)
            self.assertEqual(db.execute("SELECT count(*) FROM annual_report_runners WHERE race_id='202504010509' AND jockey_id IS NOT NULL").fetchone()[0],3)
            db.execute('''INSERT INTO annual_report_races SELECT 'source4',document_url,page_number,panel,race_number,race_date,track,
                surface,distance_m,going,off_timestamp,expected_runners,status,issues_json,metadata_json
                FROM annual_report_races WHERE race_id='202504010509' ''')
            db.execute('''INSERT INTO annual_report_runners SELECT 'source4',horse_number,finish_order,'ソース馬',jockey_name,
                horse_id,jockey_id,payload_json FROM annual_report_runners WHERE race_id='202504010509' AND horse_number=5''')
            db.execute('INSERT INTO official_identity_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       ('source4',5,'ソース馬',2020,'jra:2020100000','C.デムーロ',None,
                        'https://www.jra.go.jp/source','a'*64,'2026-10-19T00:00:00+00:00',json.dumps(dict(jockey_name='C.デムーロ'))))
            propagate(db)
            self.assertEqual(db.execute("SELECT count(*) FROM annual_report_runners WHERE race_id='202504010509' AND jockey_id IS NOT NULL").fetchone()[0],0)
            db.close()

    def deployment_fixture(self,root):
        _,model=trained()
        artifact={**model.to_dict(),'research_only':True,'allow_missing_jockey':True}
        mp=Path(root)/'research.json';mp.write_text(json.dumps(artifact))
        report=dict(model_artifact_sha256=digest(artifact),evaluation_races=3,
                    candidate={'top1_hit':1/3},fixed_top1_100yen={'return_pct':70})
        rp=Path(root)/'report.json';rp.write_text(json.dumps(report))
        folder=Path(root)/'deploy';activate(mp,rp,folder)
        dbpath=Path(root)/'history.sqlite';db=connect(dbpath);schema(db);db.close()
        rows=field(2030)
        now=dt.datetime.now(dt.timezone.utc).isoformat()
        for r in rows:
            r.update(jockey_id=None,going=None,features_asof=now)
            for k in ('finish_position','final_win_odds','going_asof'):
                r.pop(k,None)
        return dbpath,rows,folder/'active_manifest.json'

    def test_active_probability_path_runs_without_current_odds_or_fake_ids(self):
        with tempfile.TemporaryDirectory() as root:
            db,rows,manifest=self.deployment_fixture(root)
            prediction=forecast(db,rows,manifest)
            self.assertEqual(prediction['deployment_status'],'experimental_probability')
            self.assertAlmostEqual(sum(r['p_first'] for r in prediction['runners']),1)
            self.assertTrue(all(r['jockey_id'] is None for r in prediction['runners']))
            self.assertEqual(prediction['allocation']['stake_yen'],0)
            artifact=json.loads(manifest.with_name('active_model.json').read_text())
            with self.assertRaises(ValueError):HierarchicalModel.from_dict(artifact)

    def test_live_path_rejects_final_odds_future_snapshot_and_tampering(self):
        with tempfile.TemporaryDirectory() as root:
            db,rows,manifest=self.deployment_fixture(root)
            with self.assertRaisesRegex(ValueError,'post-race'):
                forecast(db,[{**r,'final_win_odds':2} for r in rows],manifest)
            with self.assertRaisesRegex(ValueError,'future'):
                forecast(db,[{**r,'features_asof':'2030-01-01T00:00:00+09:00'} for r in rows],manifest)
            now=dt.datetime.now(dt.timezone.utc)
            expired=[{**r,'off_timestamp':(now-dt.timedelta(minutes=1)).isoformat(),
                      'features_asof':(now-dt.timedelta(hours=1)).isoformat()} for r in rows]
            with self.assertRaisesRegex(ValueError,'cutoff has already passed'):
                forecast(db,expired,manifest)
            mp=manifest.with_name('active_model.json');artifact=json.loads(mp.read_text())
            artifact['weights'][0]+=1;mp.write_text(json.dumps(artifact))
            with self.assertRaisesRegex(ValueError,'checksum'):forecast(db,rows,manifest)


if __name__=='__main__':unittest.main()
