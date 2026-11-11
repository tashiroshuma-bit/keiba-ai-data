"""Fail-closed V51 canonical 14-feature 2025 retrain driver tests.

These fixtures do not contain real historical 2025 data and never assert
a 14-feature accuracy improvement.
"""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.v51_fouraxis_complete_real_run import (
    inspect_sqlite,execute,_printable
)

class FourAxisActualRunSourceGate(unittest.TestCase):
    def test_missing_actual_database_fails_before_model(self):
        with tempfile.TemporaryDirectory() as temp:
            t=Path(temp)
            with self.assertRaisesRegex(FileNotFoundError,"required source"):
                execute(t/"missing.sqlite",t/"missing_overlay.sqlite",
                        t/"history.py",t/"model.json",t/"output")
            self.assertFalse((t/"output").exists())

    def test_noncanonical_db_rejected_before_feature_extraction(self):
        with tempfile.TemporaryDirectory() as temp:
            t=Path(temp)
            sample=t/"invalid.sqlite"
            sample.write_bytes(b"not the v12 canonical JRA source")
            with self.assertRaisesRegex(ValueError,"bytes differ"):
                inspect_sqlite(sample,"a"*64,362139648)
            self.assertTrue(sample.is_file())

    def test_summary_denominators_and_disclosures_are_explicit(self):
        base={"races":594,"top1_accuracy":.25,"winner_logloss":2.25,
              "winner_brier":.865,"ece_confidence":.031}
        valid={"valid_unique_podium_races":590,
                "ordered_exact_hits":5,"unordered_exact_hits":20}
        x={"2025_late_confirmation":{
                "original":base,"candidate":dict(base),
                "podium_original":valid,"podium_selected":dict(valid),
                "strict_gate_pass":False},
            "2025_full_year_descriptive_in_sample_calibration":{
                "baseline":{**base,"races":2925},
                "selected_proposal":{**base,"races":2925}},
            "2026_frozen_audit_only":{
                "original_official_v51":{**base,"races":2411},
                "selected_research_proposal_not_promoted":{**base,"races":2411},
                "podium_original":{**valid,"valid_unique_podium_races":2400},
                "podium_selected_proposal_not_promoted":{
                    **valid,"valid_unique_podium_races":2400}},
            "chosen_on_2025_search_only":"jockey_condition_ridge_0.03"}
        s=_printable(x)
        self.assertIn("2025後期・独立確認",s)
        self.assertIn("2025全期",s)
        self.assertIn("2026固定事後監査",s)
        self.assertIn("5/590",s)
        self.assertIn("現行Brier",s)
        self.assertIn("現行ECE",s)
        self.assertIn("False",s)
        self.assertIn("使用していない",s)

if __name__=="__main__":
    unittest.main()
