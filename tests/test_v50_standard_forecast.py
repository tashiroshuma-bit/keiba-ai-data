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
