"""Real V51 rank ablation audit locks: facts, denominators, non-promotion."""
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/"reports/v51_real_2025_2026_rank_ablation_full_20261111.json"

class V51RealRankAblation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d=json.loads(REPORT.read_text(encoding="utf-8"))
    def test_immutable_real_source_sha_and_cohort(self):
        d=self.d
        self.assertEqual(d["source_evidence"]["db_sha256"],
                         "5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd")
        self.assertEqual(d["source_evidence"]["overlay_sha256"],
                         "5f80b199b61b401fb046a0d7c2fb065b8c433dbc5734fcbefb5f0740ae3d03ea")
        self.assertEqual(d["population"]["training_2023_2024_validated_races"],5865)
        self.assertEqual(d["population"]["2025_date_fit_races"]+
                         d["population"]["2025_date_search_races"]+
                         d["population"]["2025_date_confirmation_races"],2925)
        self.assertEqual(d["population"]["2026_fixed_audit_races"],2411)
    def test_winner_rank_did_not_pass_2025_acceptance(self):
        q=self.d["winner_rank"]
        self.assertEqual(q["chosen_2025_middle"],"recent_form_x1.25")
        self.assertEqual((q["2025_late_baseline"]["hits"],
                          q["2025_late_chosen"]["hits"]),(149,154))
        self.assertFalse(q["2025_late_gate_passed"])
        self.assertLessEqual(q["2025_late_paired_day_bootstrap95_delta_accuracy"][0],0.)
        self.assertGreater(q["2025_late_chosen"]["winner_logloss"],
                           q["2025_late_baseline"]["winner_logloss"])
    def test_second_third_winner_coefficients_unchanged(self):
        q=self.d["conditional_podium"]
        self.assertEqual(q["chosen_2025_middle"],
                         {"ridge_second":0.03,"ridge_third":0.003})
        before=q["2025_late_baseline"]
        after=q["2025_late_candidate"]
        self.assertEqual(before["top1_hits"],after["top1_hits"])
        self.assertEqual(round(before["ordered_podium_exact"]*594),
                         round(after["ordered_podium_exact"]*594))
        self.assertFalse(q["2025_late_gate_passed"])
        self.assertEqual(round(q["2026_fixed_evaluation_post_selection"]["official_v51"]["ordered_podium_exact"]*2411),32)
        self.assertEqual(round(q["2026_fixed_evaluation_post_selection"]["candidate_recalibrated_using_2025_only"]["ordered_podium_exact"]*2411),29)
    def test_official_v51_never_replaced(self):
        self.assertFalse(self.d["production"]["official_coefficients_modified"])
        self.assertFalse(self.d["production"]["source_v50_used"])
        self.assertEqual(self.d["production"]["official_version"],"v51")
if __name__=="__main__":unittest.main()
