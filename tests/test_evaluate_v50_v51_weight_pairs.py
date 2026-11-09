import unittest
from scripts.capture_v50_bodyweight import capture
from scripts.evaluate_v50_v51_weight_pairs import evaluate
from tests.test_capture_v50_bodyweight import sample

class PairedEvaluationTests(unittest.TestCase):
    def setUp(self):
        v,w=sample()
        self.record=capture(v,w,v50_hash="f"*64,weight_hash="0"*64)
        self.result={"observed_at":"2026-11-14T12:00:00+09:00",
                     "races":[{"race":"2026-11-14 Tokyo 1R","finish_order":[1,3,2]}]}

    def test_evaluate_metrics(self):
        out=evaluate(self.record,self.result)
        self.assertEqual(out["evaluation_races"],1)
        self.assertEqual(out["metrics"]["v50"]["winner_hit"],1)
        self.assertGreater(out["metrics"]["v50"]["logloss"],0)
        self.assertEqual(out["metrics"]["v50"]["unordered_podium_hit"],1)
        self.assertEqual(out["status"],"PAIRED_HISTORICAL_EVALUATION_NO_AUTOMATIC_PROMOTION")

    def test_refuse_result_before_off(self):
        self.result["observed_at"]="2026-11-14T09:30:00+09:00"
        with self.assertRaises(ValueError):evaluate(self.record,self.result)

    def test_refuse_incomplete_results(self):
        self.result["races"][0]["finish_order"]=[1,3]
        with self.assertRaises(ValueError):evaluate(self.record,self.result)

    def test_refuse_wrong_race(self):
        self.result["races"][0]["race"]="2026-11-14 Tokyo 2R"
        with self.assertRaises(ValueError):evaluate(self.record,self.result)

if __name__=="__main__":unittest.main()
