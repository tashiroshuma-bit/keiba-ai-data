import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from scripts.jra_official_race_id_import import import_results
URL="https://www.jra.go.jp/JRADB/accessS.html?CNAME=pw01sde1001202301010120230722%2F4A"
class OfficialImporterTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.db=self.root/"canonical.sqlite"
        c=sqlite3.connect(self.db)
        c.execute("CREATE TABLE annual_report_races(race_id TEXT,status TEXT)")
        c.execute("INSERT INTO annual_report_races VALUES ('202301010101','validated_result')")
        c.execute("CREATE TABLE annual_report_runners(race_id TEXT,horse_number INTEGER,horse_name TEXT,horse_id TEXT)")
        c.execute("INSERT INTO annual_report_runners VALUES('202301010101',5,'サトミノキラリ',NULL)")
        c.execute("INSERT INTO annual_report_runners VALUES('202301010101',2,'別の馬',NULL)")
        c.execute("INSERT INTO annual_report_runners VALUES('202301010101',3,'既知馬','jra:2021103333')")
        c.commit();c.close()
        self.source=self.root/"raw";self.source.mkdir()
        def row(num,name,hid):
            return f'<tr><td>1</td><td>枠</td><td>{num}</td><td><a href="/JRADB/accessU.html?CNAME=pw01dud10{hid[4:]}/AB">{name}</a></td></tr>'
        original=("<table><tbody>"+
            row(5,"サトミノキラリ","jra:2021101429")+
            row(2,"一致しない馬","jra:2021101111")+
            row(3,"既知馬","jra:2021103333")+"</tbody></table>").encode("cp932")
        h=hashlib.sha256(original).hexdigest();(self.source/(h+".bin")).write_bytes(original)
        self.manifest=self.root/"official_race_horse_ids.json"
        self.data={"schema":"jra-official-raw-results-horse-id-recovery-v1",
             "records":[{"race_id":"202301010101","source_url":URL,"source_sha256":h,
                 "observed_at":"2026-11-10T03:55:18+00:00","horses":[
                    {"horse_number":5,"horse_name":"サトミノキラリ","horse_id":"jra:2021101429"},
                    {"horse_number":2,"horse_name":"一致しない馬","horse_id":"jra:2021101111"},
                    {"horse_number":3,"horse_name":"既知馬","horse_id":"jra:2021103333"}]}]}
        self.manifest.write_text(json.dumps(self.data))
    def tearDown(self):self.tmp.cleanup()
    def test_only_exact_official_race_number_name_and_id_pass(self):
        out=import_results(self.db,self.manifest,self.root/"out")
        self.assertEqual(out["newly_verified"],1)
        self.assertEqual(out["rejected"],1)
        audit=json.loads((self.root/"out"/"audit.json").read_text())
        self.assertEqual(audit["links"][0]["horse_id"],"jra:2021101429")
        self.assertEqual(audit["links"][0]["evidence_level"],"JRA_OFFICIAL_RACE_ROW_DIRECT")
        conn=sqlite3.connect(self.db)
        self.assertIsNone(conn.execute("SELECT horse_id FROM annual_report_runners WHERE horse_number=5").fetchone()[0])
        conn.close()
    def test_source_sha_mismatch_rejected(self):
        self.data["records"][0]["source_sha256"]="a"*64
        self.manifest.write_text(json.dumps(self.data))
        with self.assertRaises((ValueError,FileNotFoundError)):
            import_results(self.db,self.manifest,self.root/"tamper")
    def test_canonical_existing_id_conflict_rejected(self):
        c=sqlite3.connect(self.db)
        c.execute("UPDATE annual_report_runners SET horse_id='jra:2021109999' WHERE horse_number=5")
        c.commit();c.close()
        with self.assertRaisesRegex(ValueError,"conflict"):
            import_results(self.db,self.manifest,self.root/"conflict")
if __name__=="__main__":unittest.main()
