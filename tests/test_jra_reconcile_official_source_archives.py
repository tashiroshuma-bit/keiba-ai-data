import hashlib
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from scripts.jra_reconcile_official_source_archives import reconcile

URL='https://www.jra.go.jp/JRADB/accessS.html?CNAME=pw01sde1001202301010120230722%2F4A'

class ReconcileOriginalJRAEvidence(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.canonical=self.root/'canonical.sqlite'
        c=sqlite3.connect(self.canonical)
        c.execute('CREATE TABLE annual_report_races(race_id TEXT,race_date TEXT,status TEXT)')
        c.execute('CREATE TABLE annual_report_runners(race_id TEXT,horse_number INTEGER,horse_name TEXT,horse_id TEXT)')
        c.execute("INSERT INTO annual_report_races VALUES('202301010101','2023-07-22','validated_result')")
        c.executemany('INSERT INTO annual_report_runners VALUES (?,?,?,?)',[
            ('202301010101',1,'(cid:10)ノーブルロジャー',None),
            ('202301010101',2,'別名正確',None),
            ('202301010101',3,'既知馬','jra:2021100003')])
        c.commit();c.close()
        self.prior=self.root/'prior.sqlite'
        s=sqlite3.connect(self.prior)
        s.execute('CREATE TABLE horse_identity_overlay(race_id TEXT,horse_number INTEGER,horse_name TEXT,horse_id TEXT,race_date TEXT,method TEXT,source_url TEXT)')
        s.execute('CREATE TABLE official_direct_evidence(race_id TEXT,horse_number INTEGER,horse_id TEXT,source_url TEXT,source_sha256 TEXT,observed_at TEXT)')
        s.execute("INSERT INTO horse_identity_overlay VALUES('202301010101',2,'別名正確','jra:2021100002','2023-07-22','PROFILE_NAME_BIRTHYEAR_AGE_CORROBORATED',NULL)")
        s.commit();s.close()
        def row(num,name,hid):
            return f'<tr><td>1</td><td>枠</td><td>{num}</td><td><a href="/JRADB/accessU.html?CNAME=pw01dud10{hid[4:]}/AB">{name}</a></td></tr>'
        self.raw=('<table>'+''.join(row(*r) for r in [
            (1,'ノーブルロジャー','jra:2021100001'),(2,'別名正確','jra:2021100002'),
            (3,'既知馬','jra:2021100003')])+'</table>').encode('cp932')
        self.archive=self.root/'source.zip'
        self.build_zip(self.raw)
    def build_zip(self,raw,claimed=None):
        checksum=hashlib.sha256(raw).hexdigest()
        horses=claimed or [{'horse_number':i,'horse_name':name,'horse_id':hid} for i,name,hid in
                           [(1,'ノーブルロジャー','jra:2021100001'),(2,'別名正確','jra:2021100002'),(3,'既知馬','jra:2021100003')]]
        manifest={'schema':'jra-official-raw-results-horse-id-recovery-v1',
                 'records':[{'race_id':'202301010101','source_url':URL,
                             'source_sha256':checksum,'observed_at':'2026-11-10T10:00:00+00:00',
                             'horses':horses}]}
        with zipfile.ZipFile(self.archive,'w') as z:
            z.writestr('2023-w29/official_race_horse_ids.json',json.dumps(manifest,ensure_ascii=False))
            z.writestr('2023-w29/raw/'+checksum+'.bin',raw)
    def test_real_bytes_allow_two_direct_rows_and_candidate_upgrade(self):
        report=reconcile(self.canonical,self.prior,[self.archive],self.root/'output',expected_sha=None)
        self.assertEqual(report['new_official_direct_rows'],2)
        self.assertEqual(report['official_direct_confirmed_rows'],2)
        self.assertEqual(report['total_covered_rows_in_sidecar'],2)
        self.assertEqual(report['statistics']['pdf_cid_prefix_normalization'],1)
        self.assertEqual(report['statistics']['already_in_canonical'],1)
        self.assertFalse(report['canonical_mutated'])
        c=sqlite3.connect(self.canonical)
        self.assertEqual(c.execute('SELECT count(*) FROM annual_report_runners WHERE horse_id IS NULL').fetchone()[0],2)
        c.close()
        c=sqlite3.connect(self.root/'output'/'horse_id_overlay_source_verified.sqlite')
        self.assertEqual(c.execute('PRAGMA quick_check').fetchone()[0],'ok')
        c.close()
    def test_conflict_in_immutable_raw_claims_rejects_entire_zip(self):
        self.build_zip(self.raw,claimed=[{'horse_number':1,'horse_name':'悪意改変','horse_id':'jra:2021100001'}])
        report=reconcile(self.canonical,self.prior,[self.archive],self.root/'failure',expected_sha=None)
        self.assertEqual(report['new_official_direct_rows'],0)
        self.assertEqual(report['statistics']['archive_parse_errors'],1)
        self.assertEqual(report['total_covered_rows_in_sidecar'],1)
    def test_conflicting_prior_profile_kept_unverified(self):
        s=sqlite3.connect(self.prior)
        s.execute("UPDATE horse_identity_overlay SET horse_id='jra:2021199999' WHERE horse_number=2")
        s.commit();s.close()
        report=reconcile(self.canonical,self.prior,[self.archive],self.root/'conflict',expected_sha=None)
        self.assertEqual(report['statistics']['profile_candidate_conflicts'],1)
        self.assertEqual(report['new_official_direct_rows'],1)
    def test_duplicate_zip_source_does_not_double_assign(self):
        report=reconcile(self.canonical,self.prior,[self.archive,self.archive],self.root/'twice',expected_sha=None)
        self.assertEqual(report['new_official_direct_rows'],2)
        self.assertEqual(report['statistics']['repeat_direct_id_evidence'],2)
if __name__=='__main__':unittest.main()