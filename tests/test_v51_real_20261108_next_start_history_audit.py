"""Actual immutable Nov8 JRA data read tests, not predictive accuracy."""
import unittest
from scripts.v51_real_20261108_next_start_history_audit import audit

class V51ActualNov08HistoryFeatureAudit(unittest.TestCase):
    def test_later_2026_nov14_source_history_proof_and_coverage(self):
        d=audit(asof="2026-11-14T08:00:00+09:00",
                off="2026-11-14T10:00:00+09:00")
        self.assertEqual(d["source_db_real_jra_races"],36)
        self.assertEqual(d["counts"]["saved_postrace_horse_rows"],497)
        self.assertEqual(d["counts"]["past_history_eligible_at_target_asof"],497)
        self.assertEqual(d["counts"]["official_horse_identity_eligible"],497)
        self.assertEqual(d["counts"].get("previous_corner4_parsed",0)
                         +d["missing"].get("previous_corner4_unparsed",0),497)
        self.assertGreater(d["counts"]["previous_weight_delta_pct_valid"],0)
        self.assertFalse(d["same_race_result_used"])
        self.assertFalse(d["current_race_weight_used"])
        self.assertFalse(d["official_v51_model_updated"])
    def test_next_calendar_day_not_eligible(self):
        d=audit(asof="2026-11-09T09:00:00+09:00",
                off="2026-11-09T12:00:00+09:00")
        self.assertEqual(d["counts"]["saved_postrace_horse_rows"],497)
        self.assertNotIn("past_history_eligible_at_target_asof",d["counts"])
        self.assertEqual(d["missing"]["two_calendar_day_embargo"],497)
    def test_asof_must_precede_target_race(self):
        with self.assertRaisesRegex(ValueError,"after forecast"):
            audit(asof="2026-11-14T11:00:00+09:00",
                  off="2026-11-14T10:00:00+09:00")
if __name__=="__main__":
    unittest.main()
