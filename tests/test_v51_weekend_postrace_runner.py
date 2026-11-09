import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from scripts.v51_weekend_postrace_runner import evaluate_bundle

ASOF="2026-11-14T09:00:00+09:00"
OFF="2026-11-14T10:00:00+09:00"
RACE="2026-11-14 Tokyo 1R"

def save(path,data):path.write_text(json.dumps(data),encoding="utf8")

class WeekendPostRaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.frozen=self.root/"archive.json"
        save(self.frozen,{"schema":"jra-v50-weight-paired-preoff-v1",
           "canonical_database_sha256":"a"*64,"forecast_asof":ASOF,
           "races":[{"race":RACE,"original_off_at":OFF,"horses":[
           {"number":i,"v50_p1":p,"weight_change_bucket":"-3..+3",
            "weight_observed_at":ASOF} for i,p in ((1,.5),(2,.3),(3,.2))]}]})
        self.source=self.root/"source.bin"
        self.source.write_bytes(b"EXAMPLE ONLY ORIGINAL OFFICIAL RESULT")
        self.result=self.root/"result.json"
        self.manifest={"observed_at":"2026-11-14T12:00:00+09:00",
          "source_evidence":{"source_url":"https://www.jra.go.jp/synthetic",
             "observed_at":"2026-11-14T12:00:00+09:00",
             "original_source_sha256":hashlib.sha256(self.source.read_bytes()).hexdigest()},
          "races":[{"race":RACE,"finish_order":[1,3,2]}]}
        save(self.result,self.manifest)
    def tearDown(self):self.temp.cleanup()
    def test_end_to_end_pair_and_calibration(self):
        out=evaluate_bundle(self.frozen,self.result,self.source,self.root/"output.json")
        self.assertEqual(out["races"],1)
        r=json.loads((self.root/"output.json").read_text())
        self.assertEqual(r["evaluation"]["metrics"]["v50"]["winner_hit"],1)
        self.assertEqual(r["calibration"]["comparisons"]["v50"]["n_races"],1)
        self.assertFalse(r["v51_promoted"])
        with self.assertRaises(FileExistsError):
            evaluate_bundle(self.frozen,self.result,self.source,self.root/"output.json")
    def test_tampered_official_source_refused(self):
        self.source.write_bytes(b"TAMPER")
        with self.assertRaises(ValueError):
            evaluate_bundle(self.frozen,self.result,self.source,self.root/"other.json")
    def test_missing_full_results_refused(self):
        self.manifest["races"][0]["finish_order"]=[1,3]
        save(self.result,self.manifest)
        with self.assertRaises(ValueError):
            evaluate_bundle(self.frozen,self.result,self.source,self.root/"other.json")
    def test_reject_wrong_result_observed_at(self):
        self.manifest["observed_at"]="2026-11-14T09:00:00+09:00"
        save(self.result,self.manifest)
        with self.assertRaises(ValueError):
            evaluate_bundle(self.frozen,self.result,self.source,self.root/"other.json")
if __name__=="__main__":unittest.main()
