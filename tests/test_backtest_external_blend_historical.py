import json, tempfile, unittest
from datetime import datetime
from pathlib import Path
from scripts.backtest_external_blend_historical import validate, run

def row(i, winner=1):
    return {"race_id":f"2026-10-01-KYO-{i}","off_at":"2026-10-01T15:00:00+09:00",
        "internal_captured_at":"2026-09-30T19:00:00+09:00",
        "external_captured_at":"2026-09-30T20:00:00+09:00",
        "external_page_updated_at":"2026-09-30T18:00:00+09:00",
        "internal_model_trained_through":"2026-09-29T00:00:00+09:00",
        "horses":[{"number":1,"internal_p1":.5,"external_index":80},{"number":2,"internal_p1":.3,"external_index":70},{"number":3,"internal_p1":.2,"external_index":60}],
        "finish":[winner,2 if winner!=2 else 1,3 if winner!=3 else 1]}
class HistoricalTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate(row(1))["race_id"],"2026-10-01-KYO-1")
    def test_future_prediction_rejected(self):
        r=row(1);r["external_page_updated_at"]="2026-10-01T15:01:00+09:00"
        with self.assertRaises(ValueError):validate(r)
    def test_future_trained_model_rejected(self):
        r=row(1);r["internal_model_trained_through"]="2026-10-01T16:00:00+09:00"
        with self.assertRaises(ValueError):validate(r)
    def test_incomplete_data_is_not_backtest(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"data.jsonl";p.write_text(json.dumps(row(1))+"\n")
            r=run(p,100)
            self.assertEqual(r["status"],"INSUFFICIENT_HISTORICAL_PREOFF_DATA")
            self.assertEqual(r["accepted_races"],1)
    def test_holdout_computes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"data.jsonl";p.write_text("\n".join(json.dumps(row(i)) for i in range(1,11)))
            r=run(p,10)
            self.assertEqual(r["status"],"HOLDOUT_EVALUATED_NOT_AUTOMATICALLY_PRODUCTION_APPROVED")
            self.assertEqual(len(r["scores"]),18)
            self.assertEqual(r["scores"][0]["test_n"],3)
if __name__=="__main__":unittest.main()
