import json
import tempfile
import unittest
from pathlib import Path
from scripts.capture_v50_bodyweight import capture,immutable_save

ASOF="2026-11-14T09:00:00+09:00"
OFF="2026-11-14T10:00:00+09:00"

def sample():
    v={"version":"v50","standard_forecast":True,"live_bet_generation":False,
       "canonical_database_sha256":"a"*64,"policy_sha256":"b"*64,
       "forecast_sha256":"c"*64,"rider_sha256":"d"*64,
       "forecast_asof":ASOF,
       "races":[{"race":"2026-11-14 Tokyo 1R","v50":{"horses":[
           {"number":1,"name":"A","p1":0.5},
           {"number":2,"name":"B","p1":0.3},
           {"number":3,"name":"C","p1":0.2}]}}]}
    w={"asof":ASOF,"races":[{"race":"2026-11-14 Tokyo 1R",
        "original_off_at":OFF,"observed_at":ASOF,
        "source_url":"https://example.org/source",
        "source_sha256":"e"*64,"horses":[
            {"number":1,"body_weight_kg":480,"weight_change_kg":-4,"weight_observed_at":ASOF},
            {"number":2,"body_weight_kg":490,"weight_change_kg":None,"weight_observed_at":ASOF},
            {"number":3,"body_weight_kg":500,"weight_change_kg":10,"weight_observed_at":ASOF}]}]}
    return v,w

class PairedCaptureTest(unittest.TestCase):
    def test_complete_immutable_and_normalized(self):
        v,w=sample()
        old=json.dumps(v,sort_keys=True)
        x=capture(v,w,v50_hash="f"*64,weight_hash="0"*64)
        self.assertEqual(json.dumps(v,sort_keys=True),old)
        self.assertEqual(len(x["races"][0]["horses"]),3)
        self.assertEqual(x["races"][0]["horses"][1]["weight_change_bucket"],"unknown")
        self.assertAlmostEqual(sum(h["v50_p1"] for h in x["races"][0]["horses"]),1)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"frozen.json"
            self.assertEqual(len(immutable_save(path,x)),64)
            with self.assertRaises(FileExistsError):immutable_save(path,x)
            self.assertEqual(json.loads(path.read_text())["production_model"],"v50")

    def test_reject_future_source(self):
        v,w=sample();w["races"][0]["observed_at"]="2026-11-14T09:01:00+09:00"
        with self.assertRaises(ValueError):capture(v,w,v50_hash="f"*64,weight_hash="0"*64)

    def test_reject_late_horse_timestamp(self):
        v,w=sample();w["races"][0]["horses"][0]["weight_observed_at"]="2026-11-14T09:01:00+09:00"
        with self.assertRaises(ValueError):capture(v,w,v50_hash="f"*64,weight_hash="0"*64)

    def test_reject_after_off(self):
        v,w=sample();w["races"][0]["original_off_at"]="2026-11-14T08:00:00+09:00"
        with self.assertRaises(ValueError):capture(v,w,v50_hash="f"*64,weight_hash="0"*64)

    def test_reject_incomplete_field(self):
        v,w=sample();w["races"][0]["horses"].pop()
        with self.assertRaises(ValueError):capture(v,w,v50_hash="f"*64,weight_hash="0"*64)

    def test_reject_duplicates(self):
        v,w=sample();w["races"][0]["horses"][1]["number"]=1
        with self.assertRaises(ValueError):capture(v,w,v50_hash="f"*64,weight_hash="0"*64)

    def test_reject_bad_probabilities(self):
        v,w=sample();v["races"][0]["v50"]["horses"][0]["p1"]=0.7
        with self.assertRaises(ValueError):capture(v,w,v50_hash="f"*64,weight_hash="0"*64)

    def test_reject_mismatched_timezones_asof(self):
        v,w=sample();w["asof"]="2026-11-14T00:00:01Z"
        with self.assertRaises(ValueError):capture(v,w,v50_hash="f"*64,weight_hash="0"*64)

    def test_reject_nonstandard_forecast(self):
        v,w=sample();v["standard_forecast"]=False
        with self.assertRaises(ValueError):capture(v,w,v50_hash="f"*64,weight_hash="0"*64)

if __name__=="__main__":unittest.main()
