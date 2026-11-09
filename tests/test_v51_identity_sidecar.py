import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from scripts.v51_identity_sidecar import resolve

class IdentitySidecarTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.conn=sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE annual_report_races(race_id TEXT PRIMARY KEY,status TEXT)")
        self.conn.execute("""CREATE TABLE annual_report_runners(
            race_id TEXT,horse_number INTEGER,horse_name TEXT,horse_id TEXT)""")
        self.conn.execute("INSERT INTO annual_report_races VALUES ('2026x1','validated_result')")
        self.conn.execute("INSERT INTO annual_report_runners VALUES ('2026x1',1,'テスト馬',NULL)")
        self.evidence=b"SYNTHETIC JRA RESPONSE BYTES"
        self.sha=hashlib.sha256(self.evidence).hexdigest()
        (self.root/(self.sha+".bin")).write_bytes(self.evidence)
        self.proof=dict(race_id="2026x1",horse_number=1,horse_name="テスト馬",
            horse_id="jra:0123456789",observed_at="2026-11-09T12:00:00+09:00",
            source_url="https://www.jra.go.jp/test/example",
            source_sha256=self.sha)
    def tearDown(self):
        self.conn.close();self.tmp.cleanup()
    def test_attested_match_becomes_sidecar_only(self):
        result=resolve(self.conn,[self.proof],self.root)
        self.assertEqual(result["verified_new_links"],1)
        self.assertEqual(self.conn.execute("SELECT horse_id FROM annual_report_runners").fetchone()[0],None)
    def test_no_approximate_name(self):
        result=resolve(self.conn,[dict(self.proof,horse_name="違う馬")],self.root)
        self.assertEqual(result["verified_new_links"],0)
        self.assertIn("horse name mismatch",result["rejected"][0]["reason"])
    def test_archive_tampering_refused(self):
        (self.root/(self.sha+".bin")).write_bytes(b"TAMPERED")
        result=resolve(self.conn,[self.proof],self.root)
        self.assertEqual(result["verified_new_links"],0)
        self.assertIn("digest mismatch",result["rejected"][0]["reason"])
    def test_future_identity_not_usable_preoff(self):
        r=resolve(self.conn,[self.proof],self.root,asof="2026-11-09T11:00:00+09:00")
        self.assertEqual(r["verified_new_links"],0)
    def test_duplicate_rejected(self):
        r=resolve(self.conn,[self.proof,self.proof],self.root)
        self.assertEqual(r["verified_new_links"],1)
        self.assertEqual(len(r["rejected"]),1)
    def test_official_id_only(self):
        r=resolve(self.conn,[dict(self.proof,horse_id="horse123")],self.root)
        self.assertEqual(r["verified_new_links"],0)
if __name__=="__main__":unittest.main()
