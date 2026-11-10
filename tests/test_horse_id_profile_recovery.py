import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from scripts.horse_id_profile_recovery import recover

class HorseIDRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/"src.sqlite"
        con=sqlite3.connect(self.db)
        con.execute("CREATE TABLE annual_report_races(race_id TEXT,status TEXT,race_date TEXT)")
        con.execute("CREATE TABLE annual_report_runners(race_id TEXT,horse_number INTEGER,horse_name TEXT,horse_id TEXT,payload_json TEXT)")
        con.execute("INSERT INTO annual_report_races VALUES ('race','validated_result','2026-10-17')")
        con.execute("INSERT INTO annual_report_runners VALUES ('race',3,'テスト馬',NULL,?)",(json.dumps({"sex_age":"牡3黒鹿"}),))
        con.execute("INSERT INTO annual_report_runners VALUES ('race',4,'別馬',NULL,?)",(json.dumps({"sex_age":"牡3鹿"}),))
        con.commit();con.close()
        self.profiles=[{"horse_name":"テスト馬","horse_id":"jra:2023100001",
            "birth_year":2023,
            "official_profile_url":"https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud102023100001%2F0A"}]
    def tearDown(self):self.tmp.cleanup()
    def test_official_profile_candidate_catalog_integrity(self):
        path=Path(__file__).resolve().parents[1]/"operations/data_updates/horse_id_official_profile_candidates_20261110.json"
        catalog=json.loads(path.read_text(encoding="utf-8"))
        items=catalog["profiles"]
        self.assertEqual(len(items),33)
        self.assertEqual(len({x["horse_name"] for x in items}),len(items))
        self.assertEqual(len({x["horse_id"] for x in items}),len(items))
        for x in items:
            self.assertTrue(x["horse_id"].startswith("jra:"))
            self.assertEqual(len(x["horse_id"]),14)
            self.assertEqual(int(x["horse_id"][4:8]),x["birth_year"])
            self.assertIn(x["horse_id"][4:],x["official_profile_url"])
            self.assertTrue(x["official_profile_url"].startswith("https://www.jra.go.jp/JRADB/accessU.html?"))
    def test_one_missing_id_recovered_with_age_proof(self):
        report=recover(self.db,self.profiles)
        self.assertEqual(report["matched_rows"],1)
        self.assertEqual(report["links"][0]["horse_id"],"jra:2023100001")
        self.assertFalse(report["official_racewise_verification_complete"])
        con=sqlite3.connect(self.db)
        self.assertIsNone(con.execute("SELECT horse_id FROM annual_report_runners WHERE horse_number=3").fetchone()[0])
        con.close()
    def test_no_age_match(self):
        self.profiles[0]["birth_year"]=2022
        self.profiles[0]["horse_id"]="jra:2022100001"
        self.profiles[0]["official_profile_url"]="https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud102022100001%2F0A"
        out=recover(self.db,self.profiles)
        self.assertEqual(out["matched_rows"],0)
        self.assertEqual(len(out["rejections"]),1)
    def test_bad_profile_id_rejected(self):
        self.profiles[0]["horse_id"]="2023100001"
        with self.assertRaises(ValueError):recover(self.db,self.profiles)
    def test_no_guess_without_exact_name(self):
        self.profiles[0]["horse_name"]="テスト馬改"
        self.assertEqual(recover(self.db,self.profiles)["matched_rows"],0)
if __name__=="__main__":unittest.main()
