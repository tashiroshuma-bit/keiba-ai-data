"""Regression assertions for ACTUAL v12 14-feature V51 retraining report.

These assertions examine recorded real-race results; they do not recompute
the 362 MB experiment in GitHub CI, where the canonical SQLite is absent.
"""
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/"reports/v51_14_real_train_rank_metrics_20261113.json"
RECEIPT=ROOT/"reports/v51_14_real_run_receipt_20261113.json"
COVERAGE=ROOT/"reports/v51_14_source_coverage_20261113.json"

class RealV51FourAxisEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=json.loads(REPORT.read_text(encoding="utf-8"))
        cls.c=json.loads(COVERAGE.read_text(encoding="utf-8"))
        cls.v=json.loads(RECEIPT.read_text(encoding="utf-8"))

    def test_real_immutable_sources_and_training_population(self):
        r,c,v=self.r,self.c,self.v
        original="5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd"
        overlay="5f80b199b61b401fb046a0d7c2fb065b8c433dbc5734fcbefb5f0740ae3d03ea"
        self.assertEqual(r["source_database_sha256"],original)
        self.assertEqual(r["source_overlay_sha256"],overlay)
        self.assertEqual(c["source_db_sha256"],original)
        self.assertEqual(v["source_v12_sha256"],original)
        self.assertEqual(v["overlay_sha256"],overlay)
        self.assertEqual(r["train_races"],5865)
        self.assertEqual(r["train_runners"],80547)
        self.assertEqual(len(r["new_features"]),14)
        self.assertEqual(c["source"]["races"],11802)
        self.assertEqual(sum(x["runners"] for x in c["years"].values()),162392)
        self.assertEqual(sum((r["split_2025"][k] for k in ("early","middle","late"))),2925)

    def test_2025_live_coefficients_not_replaced_on_weak_confidence_interval(self):
        r=self.r
        p=r["confirmation_2025"]
        self.assertEqual(r["selected_candidate"],"opponent_class_ridge_0.03")
        self.assertEqual((p["baseline"]["top1_hits"],p["candidate"]["top1_hits"]),(149,157))
        self.assertEqual(p["baseline"]["races"],594)
        self.assertLess(p["candidate"]["winner_logloss"],p["baseline"]["winner_logloss"])
        self.assertLess(p["candidate"]["winner_brier"],p["baseline"]["winner_brier"])
        self.assertLessEqual(p["paired_bootstrap"]["paired_date_bootstrap95"][0],0.)
        self.assertFalse(p["strict_gate_passed"])
        self.assertFalse(r["production_enabled"])
        self.assertFalse(self.v["production_v51_changed"])

    def test_one_to_three_podium_cohorts_are_reproducible(self):
        r=self.r
        first=r["confirmation_2025"]
        self.assertEqual((first["podium_baseline"]["ordered_hits"],
                          first["podium_candidate"]["ordered_hits"]),(5,5))
        self.assertEqual((first["podium_baseline"]["unordered_hits"],
                          first["podium_candidate"]["unordered_hits"]),(19,25))
        later=r["2026_frozen_audit"]
        self.assertEqual((later["baseline"]["top1_hits"],later["candidate"]["top1_hits"]),(603,623))
        self.assertEqual((later["podium_baseline"]["ordered_hits"],
                          later["podium_candidate"]["ordered_hits"]),(32,35))
        self.assertEqual((later["podium_baseline"]["unordered_hits"],
                          later["podium_candidate"]["unordered_hits"]),(145,142))
        self.assertFalse(r["2026_used_for_selection"])
        self.assertFalse(r["current_race_result_bodyweight_used"])

    def test_all_candidates_really_trained_in_fixed_2025_middle(self):
        r=self.r
        self.assertEqual(len(r["search_2025"]),11)
        self.assertEqual(r["search_2025"]["official_baseline"]["top1_hits"],295)
        self.assertEqual(r["search_2025"]["opponent_class_ridge_0.03"]["top1_hits"],309)
        self.assertEqual(r["all_2025_in_sample_calibration"]["baseline"]["top1_hits"],719)
        self.assertEqual(r["all_2025_in_sample_calibration"]["candidate"]["top1_hits"],752)

if __name__=="__main__":
    unittest.main()
