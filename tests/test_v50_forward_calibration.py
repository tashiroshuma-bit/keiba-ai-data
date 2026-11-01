import unittest
from scripts.v50_promotion_gate import assess
from scripts.v50_forward_calibration import audit

class TestV50ForwardGate(unittest.TestCase):
    def test_unverified_and_retrospective_data_rejected(self):
        records=[{"preoff_frozen_sha256":"abc","preoff_observed_before_off":False,
                  "official_result_verified":True,"model_frozen_before_result":False,
                  "v49_p1":{1:.6,2:.3,3:.1},"v50_p1":{1:.7,2:.2,3:.1},
                  "actual_winner_number":1}]
        self.assertFalse(assess(records,min_races=1)["promotion_eligible"])
        self.assertEqual(audit(records,min_races=1)["calibration"],"not_evaluated")
    def test_valid_forward_pair_scores(self):
        record={"preoff_frozen_sha256":"abc","preoff_observed_before_off":True,
                "official_result_verified":True,"model_frozen_before_result":True,
                "v49_p1":{1:.5,2:.3,3:.2},"v50_p1":{1:.6,2:.25,3:.15},
                "actual_winner_number":1}
        result=audit([record],min_races=1)
        self.assertTrue(result["promotion_eligible"])
        self.assertLess(result["metrics"]["v50"]["logloss"],result["metrics"]["v49"]["logloss"])
    def test_regression_rejected(self):
        record={"preoff_frozen_sha256":"abc","preoff_observed_before_off":True,
                "official_result_verified":True,"model_frozen_before_result":True,
                "v49_p1":{1:.6,2:.3,3:.1},"v50_p1":{1:.3,2:.5,3:.2},
                "actual_winner_number":1}
        self.assertFalse(audit([record],min_races=1)["promotion_eligible"])

if __name__=="__main__":
    unittest.main()
