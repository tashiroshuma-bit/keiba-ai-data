import unittest
from scripts.v51_research_diagnostics import (
    audit_identity_field,preoff_feature_audit,pl_podium,calibration_diagnostic)
ASOF="2026-11-14T09:00:00+09:00"
OFF="2026-11-14T10:00:00+09:00"

def field():
    return [{"number":i,"horse_id":None,"research_features":{}} for i in (1,2,3)]

class V51DiagnosticsTest(unittest.TestCase):
    def test_missing_identity_is_explicit(self):
        r=preoff_feature_audit(field(),ASOF,OFF)
        self.assertEqual(r["identity"]["missing_ids"],3)
        self.assertEqual(r["features"]["horse_form"]["coverage"],0)
    def test_no_name_only_identity(self):
        f=field();f[0]["horse_id"]="jra:abc"
        with self.assertRaises(ValueError):audit_identity_field(f,ASOF,OFF)
    def test_refuse_future_feature(self):
        f=field();f[0]["research_features"]["rest_growth_bodyweight"]={
            "value":1.3,"observed_at":"2026-11-14T09:01:00+09:00"}
        with self.assertRaises(ValueError):preoff_feature_audit(f,ASOF,OFF)
    def test_refuse_same_day_bias_without_earlier_race(self):
        f=field();f[0]["research_features"]["day_track_bias"]={
            "value":1.0,"observed_at":ASOF}
        with self.assertRaises(ValueError):preoff_feature_audit(f,ASOF,OFF)
    def test_pl_joint_probabilities(self):
        r=pl_podium([.5,.3,.2],[1,2,3])
        self.assertAlmostEqual(r["probability_sum"],1)
        self.assertEqual(r["ordered_best"],[1,2,3])
        self.assertEqual(r["unordered_best"],[1,2,3])
        self.assertAlmostEqual(sum(v["p2"] for v in r["marginal"].values()),1)
        self.assertFalse(r["candidate_2nd_3rd_training_complete"])
    def test_rare_and_even_uncertainty(self):
        report=calibration_diagnostic([.5,.3,.2],[1,2,3])
        self.assertLess(report["uncertainty"]["normalized_entropy"],1)
        self.assertFalse(report["uncertainty"]["calibration_verified"])
    def test_reject_non_normalized(self):
        with self.assertRaises(ValueError):pl_podium([.5,.5,.5],[1,2,3])
if __name__=="__main__":unittest.main()
