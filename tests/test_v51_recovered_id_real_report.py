"""Check frozen real 2026 retrospective results without claiming fake v50 head-to-head."""
import json
import math
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def data(path):return json.loads((ROOT/path).read_bytes())
class RankRestoredIDReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=data("reports/v51_recovered_ids_cal2025_heldout2026.json")
        cls.full=data("operations/prediction_policy/v51_rank_recovered_ids_cal2025_research.json")
        cls.mask=data("operations/prediction_policy/v51_rank_old_ids_masked_control.json")
    def test_real_holdout_identical_race_population_and_no_2026_tuning(self):
        self.assertEqual(self.a["source_db_sha256"],"5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd")
        self.assertIn("NOT_V50_V51_PREOFF_PAIRED",self.a["status"])
        for mode in ("full","masked"):
            for cal in ("uncalibrated","calibrated_on_2025"):
                x=self.a["modes"][mode]["2026_"+cal]
                self.assertEqual(x["n_races"],2411)
                self.assertGreater(x["unique_podium_races"],2300)
        self.assertEqual(self.a["modes"]["full"]["2026_calibrated_on_2025"]["top1_hits"],603)
        self.assertEqual(self.a["modes"]["masked"]["2026_calibrated_on_2025"]["top1_hits"],508)
        self.assertFalse(self.full["production_enabled"])
        self.assertTrue(self.full["calibration_2025_only"])
        self.assertEqual(self.full["calibration"]["fitted_on"],"2025_validated_results_only_no_2026_reuse")
        self.assertEqual(self.mask["mode"],"masked")
    def test_all_three_stages_fitted_on_recovered_id_features(self):
        self.assertEqual(self.full["feature_count"],31)
        self.assertEqual(len(self.full["stage_coefficients"]),3)
        self.assertEqual(len(self.full["feature_names"]),31)
        for row in self.full["stage_coefficients"]:
            self.assertEqual(len(row),31)
            self.assertTrue(all(math.isfinite(v) for v in row))
        for i in ("1","2","3"):
            self.assertEqual(self.full["training_stage_audit"][i]["race_sets"],5865)
            self.assertTrue(self.full["training_stage_audit"][i]["optimizer_success"])
        self.assertNotEqual(self.mask["stage_coefficients"],self.full["stage_coefficients"])
    def test_loss_and_calibration_are_not_misreported(self):
        f=self.a["modes"]["full"]["2026_calibrated_on_2025"]
        m=self.a["modes"]["masked"]["2026_calibrated_on_2025"]
        self.assertLess(f["mean_logloss"],m["mean_logloss"])
        self.assertLess(f["mean_brier"],m["mean_brier"])
        self.assertLess(f["mean_second_marginal_logloss"],m["mean_second_marginal_logloss"])
        self.assertLess(f["mean_third_marginal_logloss"],m["mean_third_marginal_logloss"])
        self.assertLess(f["mean_conditional_second_logloss"],m["mean_conditional_second_logloss"])
        self.assertLess(f["mean_conditional_third_logloss"],m["mean_conditional_third_logloss"])
        self.assertLess(f["mean_second_marginal_brier"],m["mean_second_marginal_brier"])
        self.assertLess(f["mean_third_marginal_brier"],m["mean_third_marginal_brier"])
        self.assertGreater(f["calibration_reliability"]["ece_confidence"],m["calibration_reliability"]["ece_confidence"])
        self.assertLess(f["calibration_reliability"]["ece_confidence"],
                        self.a["modes"]["full"]["2026_uncalibrated"]["calibration_reliability"]["ece_confidence"])
        self.assertAlmostEqual(f["top1_hits"]/f["n_races"],f["top1_accuracy"],places=10)
        paired=self.a["paired_2026_calibrated"]["2026_calibrated_on_2025"]["top1_hit"]
        self.assertAlmostEqual(paired["delta"],(603-508)/2411,places=10)
        self.assertEqual(paired["n_dates"],89)
if __name__=="__main__":unittest.main()
