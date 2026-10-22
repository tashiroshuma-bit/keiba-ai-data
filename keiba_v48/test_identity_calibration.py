import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from annual_reports import connect
from official_linkage import printed_age, schema, attest, propagate, parse_result
import test_official_linkage as linkage_tests
from test_official_linkage import fixture, URL
from observed_identity import identity_observations
from enriched_features import load_observed_enriched
from ranking_model import joint_distribution, picks
from exact_rank_model import exact_set
from rank_calibration import mix_joint, validate_artifact
from confidence_calibration import alpha_for
from preoff_snapshot import audit_snapshot, static_card_status


class IdentityCalibrationTests(unittest.TestCase):
    def test_pdf_font_identifier_is_never_age(self):
        self.assertEqual(printed_age('(cid:8)3鹿'),3)
        self.assertEqual(printed_age('牡１０鹿'),10)
        self.assertIsNone(printed_age('(cid:8)鹿'))
        self.assertIsNone(printed_age('牡99'))

    def test_cid_birth_repair_restores_only_exact_attested_identity(self):
        with tempfile.TemporaryDirectory() as root:
            _,db=linkage_tests.OfficialLinkageTests().db_fixture(root)
            meta=dict(url=URL,sha256='a'*64,observed_at='2026-10-19T00:00:00+00:00')
            attest(db,parse_result(fixture(),URL),meta)
            payload=json.loads(db.execute('SELECT payload_json FROM annual_report_runners WHERE horse_number=6').fetchone()[0])
            payload['sex_age']='(cid:8)5鹿'
            db.execute('UPDATE annual_report_runners SET payload_json=? WHERE horse_number=6',(json.dumps(payload),))
            propagate(db)
            self.assertEqual(db.execute('SELECT horse_id FROM annual_report_runners WHERE horse_number=6').fetchone()[0],'jra:2020100678')
            self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())
            db.close()

    def test_profile_observation_cannot_be_replaced_by_older_anchor(self):
        with tempfile.TemporaryDirectory() as root:
            _,db=linkage_tests.OfficialLinkageTests().db_fixture(root)
            meta=dict(url=URL,sha256='a'*64,observed_at='2026-10-19T00:00:00+00:00')
            row=parse_result(fixture(),URL)[0];attest(db,[row],meta);propagate(db)
            db.execute('INSERT INTO official_profile_start_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (row['race_id'],6,row['horse_id'],row['horse_name'],row['race_date'],row['jockey_name'],row['jockey_id'],
                 'https://www.jra.go.jp/profile','b'*64,'2026-10-21T00:00:00+00:00','{}'))
            db.execute("UPDATE annual_identity_links SET horse_match_method='exact_profile_start_and_attested_horse',jockey_match_method='exact_profile_start_and_attested_horse' WHERE horse_number=6")
            times,errors=identity_observations(db)
            self.assertEqual(times[row['race_id'],'6'],dt.datetime(2026,10,21,tzinfo=dt.timezone.utc))
            self.assertFalse(errors)
            db.commit()
            history=[dict(race_id=row['race_id'],horse_number='6',horse_id=row['horse_id'],
                          result_observed_at='2026-10-19T00:00:00+00:00')]
            with patch('enriched_features.load_archive',return_value=(history,[],{})):
                self.assertEqual(load_observed_enriched(Path(root)/'test.sqlite',dt.datetime(2026,10,20,tzinfo=dt.timezone.utc)),[])
                ready=load_observed_enriched(Path(root)/'test.sqlite',dt.datetime(2026,10,22,tzinfo=dt.timezone.utc))
                self.assertEqual(ready[0]['result_available_at'],'2026-10-21T00:00:00+00:00')
            db.execute("DELETE FROM official_profile_start_evidence")
            times,errors=identity_observations(db)
            self.assertNotIn((row['race_id'],'6'),times)
            self.assertEqual(errors['missing_or_mismatched_identity_proof'],1)
            db.close()

    def test_three_race_alias_waits_for_third_observation(self):
        with tempfile.TemporaryDirectory() as root:
            _,db=linkage_tests.OfficialLinkageTests().db_fixture(root)
            row=parse_result(fixture(),URL)[0]
            for day,rid in ((19,'202504010509'),(20,'202504010510'),(21,'202504010511')):
                if rid!=row['race_id']:
                    db.execute('INSERT INTO annual_report_races SELECT ?,document_url,page_number,panel,10,race_date,track,surface,distance_m,going,off_timestamp,expected_runners,status,issues_json,metadata_json FROM annual_report_races LIMIT 1',(rid,))
                    db.execute('INSERT INTO annual_report_runners SELECT ?,horse_number,finish_order,horse_name,jockey_name,horse_id,jockey_id,payload_json FROM annual_report_runners WHERE race_id=? AND horse_number=5',(rid,row['race_id']))
                db.execute("UPDATE annual_report_runners SET jockey_name='田隼人' WHERE race_id=? AND horse_number=5",(rid,))
                attest(db,[{**row,'race_id':rid}],dict(url=URL,sha256='a'*64,observed_at=f'2026-10-{day}T00:00:00+00:00'))
            propagate(db)
            db.execute("UPDATE annual_report_runners SET jockey_name='田隼人' WHERE race_id=? AND horse_number=6",(row['race_id'],))
            propagate(db)
            times,errors=identity_observations(db)
            self.assertEqual(times[row['race_id'],'6'],dt.datetime(2026,10,21,tzinfo=dt.timezone.utc))
            self.assertFalse(errors)
            db.execute("INSERT INTO annual_report_documents(url,year,venue,meeting,day,status,fetched_at) VALUES('https://www.jra.go.jp/later.pdf',2025,'niigata',1,5,'parsed','2026-10-23T00:00:00+00:00')")
            db.execute("UPDATE annual_report_races SET document_url='https://www.jra.go.jp/later.pdf' WHERE race_id='202504010511'")
            times,errors=identity_observations(db)
            self.assertEqual(times[row['race_id'],'6'],dt.datetime(2026,10,23,tzinfo=dt.timezone.utc))
            self.assertFalse(errors);db.close()

    def test_profile_link_is_not_reused_after_annual_reparse(self):
        with tempfile.TemporaryDirectory() as root:
            _,db=linkage_tests.OfficialLinkageTests().db_fixture(root)
            meta=dict(url=URL,sha256='a'*64,observed_at='2026-10-19T00:00:00+00:00')
            row=parse_result(fixture(),URL)[0];attest(db,[row],meta)
            db.execute('INSERT INTO official_profile_start_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (row['race_id'],6,row['horse_id'],row['horse_name'],row['race_date'],row['jockey_name'],row['jockey_id'],
                 'https://www.jra.go.jp/profile','b'*64,'2026-10-21T00:00:00+00:00','{}'))
            propagate(db)
            self.assertEqual(db.execute('SELECT horse_id FROM annual_report_runners WHERE horse_number=6').fetchone()[0],row['horse_id'])
            db.execute("UPDATE annual_report_runners SET horse_name='別の馬' WHERE horse_number=6")
            propagate(db)
            self.assertIsNone(db.execute('SELECT horse_id FROM annual_report_runners WHERE horse_number=6').fetchone()[0])
            db.close()

    def test_joint_mixture_preserves_all_decisions_and_coherence(self):
        for n in (3,5,18):
            p,q=joint_distribution(np.random.default_rng(n).normal(size=(3,n))*3)
            numbers=list(map(str,range(1,n+1)));old=picks(p,q,numbers);oldset=exact_set(q,numbers)[0]
            for alpha in (.1,.9):
                pp,qq=mix_joint(p,q,alpha)
                new=picks(pp,qq,numbers)
                self.assertEqual(new[0],old[0]);self.assertEqual(set(new[1]),set(old[1]));self.assertEqual(new[2],old[2])
                self.assertEqual(exact_set(qq,numbers)[0],oldset)
                np.testing.assert_allclose(pp.sum(axis=0),1)
                np.testing.assert_allclose(pp[:,0],qq.sum(axis=(1,2)))
                self.assertTrue(np.all(pp.sum(axis=1)<=1+1e-12))
                self.assertAlmostEqual(float(qq.sum()),1)
        with self.assertRaises(ValueError):mix_joint(p,q,1)

    def test_calibration_is_bound_to_model_and_selection(self):
        data=dict(schema='keiba-rank-uniform-joint-calibration-v1',alpha=.1,model_sha256='a',
                  base_selection_sha256='b',selection_year=2024,research_only=True)
        self.assertEqual(validate_artifact(data,'a','b'),.1)
        with self.assertRaises(ValueError):validate_artifact(data,'x','b')
        band={**data,'schema':'keiba-rank-confidence-calibration-v1',
              'bands':[dict(lower=0,upper=.4,alpha=.1),dict(lower=.4,upper=1.00000001,alpha=.3)]}
        self.assertEqual(alpha_for(band,np.array([[.8,0,0],[.2,0,0]]),'a','b'),.3)
        with self.assertRaises(ValueError):alpha_for({**band,'bands':[]},np.ones((3,3))/3,'a','b')

    def test_preoff_weights_and_going_need_actual_field_evidence(self):
        now=dt.datetime(2026,10,25,3,tzinfo=dt.timezone.utc);cutoff=now+dt.timedelta(hours=3)
        row=dict(off_timestamp=(cutoff+dt.timedelta(minutes=5)).isoformat(),carried_weight=57,
            carried_weight_basis='announced_preoff',carried_weight_asof=now.isoformat(),
            carried_weight_source_url='https://www.jra.go.jp/card',carried_weight_source_sha256='a'*64,
            going='良',going_asof=now.isoformat(),going_source_url='https://www.jra.go.jp/going',going_source_sha256='b'*64)
        self.assertEqual(audit_snapshot([row],now,cutoff)['present']['carried_weight'],1)
        for invalid in ({'carried_weight_basis':'final_result'}, {'going_source_sha256':None},
                        {'going_asof':(now-dt.timedelta(days=1)).isoformat()}):
            with self.assertRaises(ValueError):audit_snapshot([{**row,**invalid}],now,cutoff)
        self.assertEqual(audit_snapshot([{'off_timestamp':row['off_timestamp']}],now,cutoff)['missing']['going'],1)

    def test_publication_notice_is_not_a_complete_field(self):
        body='<p>菊花賞の出馬表は、2026年10月22日に公開予定です。</p>'.encode()
        meta=dict(url='https://www.jra.go.jp/keiba/g1/kikka/syutsuba.html',sha256=hashlib.sha256(body).hexdigest(),status=200)
        status=static_card_status(body,meta)
        self.assertEqual(status['status'],'publication_pending')
        self.assertFalse(status['full_field_attested']);self.assertFalse(status['forecast_created'])
        with self.assertRaises(ValueError):static_card_status(body+b'x',meta)


if __name__=='__main__':unittest.main()
