import hashlib
import json
import sqlite3
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from scripts.standard_v50_forecast import standard_forecast

class StandardV50Test(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d=Path(self.tmp.name)
        self.db=d/"canonical.sqlite"
        con=sqlite3.connect(self.db)
        con.execute("CREATE TABLE annual_report_races(race_id TEXT,race_date TEXT,surface TEXT,status TEXT,expected_runners INTEGER)")
        con.execute("CREATE TABLE annual_report_runners(race_id TEXT,horse_number INTEGER,horse_id TEXT,jockey_id TEXT,finish_order INTEGER)")
        for date in ("2026-10-20","2026-10-21","2026-10-31"):
            con.execute("INSERT INTO annual_report_races VALUES (?,?,?,?,?)",(date,date,"turf","validated_result",3))
            for n in range(1,4):
                con.execute("INSERT INTO annual_report_runners VALUES (?,?,?,?,?)",(date,n,"horse"+str(n),"jra:"+str(n),n))
        con.commit();con.close()
        self.state=d/"state.json"
        self.state.write_text(json.dumps({"database":{"version":10,"sha256":hashlib.sha256(self.db.read_bytes()).hexdigest()}, "standard_forecast":{"version":"v50","policy":"operations/prediction_policy/standard_v50.json","entrypoint":"scripts/standard_v50_forecast.py","adopted_by_user":True}}))
        self.policy=d/"policy.json"
        self.policy.write_text(json.dumps({"standard_version":"v50","standard_for_future_races":True,
        "history_lag_days":2,"overlay_weight":1.0,"probability_temperature":.7,
        "live_bet_generation":False,"forecast_entrypoint":"scripts/standard_v50_forecast.py"}))
        self.forecast=d/"forecast.json"
        self.data={"source_model":"A","asof":"2026-11-01T09:00:00+09:00",
            "races":[{"race":"synthetic","surface":"turf","original_off_at":"2026-11-01T11:00:00+09:00",
                "horses":[{"number":i,"name":"horse"+str(i),"jockey_id":"jra:"+str(i),"p1":p}
                          for i,p in [(1,.5),(2,.3),(3,.2)]]}]}
        self.forecast.write_text(json.dumps(self.data))
        self.out=d/"out.json"
    def run_forecast(self):
        return standard_forecast(self.forecast,self.db,self.out,
                                 state_path=self.state,policy_path=self.policy)
    def test_full_standard_forecast_and_no_bets(self):
        r=self.run_forecast()
        self.assertEqual(r["version"],"v50")
        self.assertTrue(r["standard_forecast"])
        self.assertFalse(r["live_bet_generation"])
        self.assertEqual(r["calibration_temperature"],.7)
        self.assertEqual(len(r["races"]),1)
        self.assertEqual(r["races"][0]["rider_coverage"],3)
        self.assertTrue(self.out.exists())
        with self.assertRaises(FileExistsError):self.run_forecast()
    def test_standard_forecast_streams_large_canonical_db(self):
        original=Path.read_bytes
        canonical=self.db
        def guarded(path):
            if Path(path)==canonical:
                raise AssertionError("canonical DB must not be loaded fully into RAM")
            return original(path)
        with mock.patch.object(Path,"read_bytes",guarded):
            result=self.run_forecast()
        self.assertTrue(result["standard_forecast"])
        self.assertTrue(self.out.exists())

    def test_v51_research_same_asof_fully_proven_parallel(self):
        from scripts.standard_v50_forecast import standard_forecast
        feature_path=Path(self.tmp.name)/"v51.json"
        source={"race":"synthetic","race_id":"test-race",
                "forecast_asof":self.data["asof"],
                "race_off_at":self.data["races"][0]["original_off_at"],
                "horses":[]}
        for h in self.data["races"][0]["horses"]:
            source["horses"].append({
                "number":h["number"],"horse_id":f"jra:201710000{h['number']}",
                "feature_values":[0.0]*34,
                "feature_evidence":{
                    "source_url":"https://www.jra.go.jp/datafile/seiseki/report/2026/older.pdf",
                    "source_sha256":"a"*64,
                    "off_at":"2026-10-18T12:00:00+09:00",
                    "published_at":"2026-10-20T08:00:00+09:00",
                    "observed_at":"2026-10-22T08:00:00+09:00"},
                "official_identity_proof":{
                    "race_id":"test-race","horse_number":h["number"],
                    "horse_name":h["name"],
                    "horse_id":f"jra:201710000{h['number']}",
                    "source_url":"https://www.jra.go.jp/JRADB/accessS.html",
                    "source_sha256":"b"*64,
                    "observed_at":"2026-10-23T08:00:00+09:00"}})
        feature_path.write_text(json.dumps({"races":[source]}))
        result=standard_forecast(self.forecast,self.db,self.out,
            state_path=self.state,policy_path=self.policy,
            v51_research_features_path=feature_path)
        self.assertEqual(result["version"],"v50")
        self.assertTrue(result["v51_research_parallel"]["original_v50_unchanged"])
        self.assertFalse(result["v51_research_parallel"]["production_promotion"])
        self.assertEqual(len(result["v51_research_parallel"]["races"]),1)
        self.assertEqual(result["v51_research_parallel"]["races"][0]["field_size"],3)

    def test_v51_research_rejects_mismatched_asof(self):
        from scripts.standard_v50_forecast import standard_forecast
        feature_path=Path(self.tmp.name)/"v51_wrong.json"
        feature_path.write_text(json.dumps({"races":[{
            "race":"synthetic",
            "forecast_asof":"2026-11-01T11:10:00+09:00",
            "race_off_at":self.data["races"][0]["original_off_at"],
            "horses":[]}]}))
        with self.assertRaisesRegex(ValueError,"do not match"):
            standard_forecast(self.forecast,self.db,self.out,
                state_path=self.state,policy_path=self.policy,
                v51_research_features_path=feature_path)

    def test_reject_postoff_source(self):
        self.data["races"][0]["original_off_at"]="2026-11-01T08:00:00+09:00"
        self.forecast.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError,"pre-off"):self.run_forecast()
    def test_reject_wrong_source_model(self):
        self.data["source_model"]="D"
        self.forecast.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError,"internal A"):self.run_forecast()
    def test_reject_unverified_database(self):
        con=sqlite3.connect(self.db);con.execute("INSERT INTO annual_report_races VALUES('x','2026-01-01','turf','validated_result',3)")
        con.commit();con.close()
        with self.assertRaisesRegex(ValueError,"SHA256"):self.run_forecast()

if __name__=="__main__":
    unittest.main()
