"""Real gate-policy regression tests; no simulated metrics are reported as model quality."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v50_promotion_gate import evaluate

STATE = {"database":{"version":10,"sha256":"db-hash"},"active_model":{"live_bet_generation":False}}
def race(i):
    return {"race_id":str(i),"prediction_sha256":"pred","input_sha256":"input",
            "result_sha256":"result","frozen_before_off":True,
            "roster_independently_verified":True,"result_independently_verified":True,
            "no_postoff_features":True}
def complete():
    return {"candidate_version":"v50","canonical_db_sha256":"db-hash",
            "candidate_model_sha256":"weights",
            "independent_calibration":{"verified":True,"source_hash":"calib"},
            "races":[race(i) for i in range(100)],
            "independent_metrics":{k:0.1 for k in
                ("winner_hit","top3_all_hit","ordered_all_hit","mean_rank_log_loss","brier")},
            "replay_verified":True,"all_ci_passed":True}
class PromotionGateTest(unittest.TestCase):
    def test_requires_evidence(self):
        outcome=evaluate(STATE,{})
        self.assertFalse(outcome["approved"])
        self.assertIn("100 forward races required",outcome["failures"])
    def test_rejects_postoff_leakage(self):
        data=complete();data["races"][4]["no_postoff_features"]=False
        self.assertFalse(evaluate(STATE,data)["approved"])
    def test_rejects_duplicate(self):
        data=complete();data["races"][3]["race_id"]="2"
        self.assertFalse(evaluate(STATE,data)["approved"])
    def test_rejects_unverified_calibration(self):
        data=complete();data["independent_calibration"]["verified"]=False
        self.assertFalse(evaluate(STATE,data)["approved"])
    def test_accepts_complete_evidence_structure(self):
        self.assertTrue(evaluate(STATE,complete())["approved"])
if __name__ == "__main__":
    unittest.main()
