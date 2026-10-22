import unittest
from rank_target_uncertainty import evaluate, wilson


class RankTargetUncertaintyTests(unittest.TestCase):
    def test_zero_hits(self):
        low, high = wilson(0, 100)
        self.assertEqual(low, 0)
        self.assertGreater(high, 0)

    def test_full_hits(self):
        low, high = wilson(100, 100)
        self.assertEqual(high, 1)
        self.assertLess(low, 1)

    def test_target_not_met_from_point_only(self):
        result = evaluate({"winner_hit": 80, "ordered_all_hit": 50,
                           "top3_all_hit": 60}, 100)
        self.assertTrue(result["all_point_targets_met"])
        self.assertFalse(result["all_lower_bound_targets_met"])

    def test_invalid_counts(self):
        with self.assertRaises(ValueError):
            wilson(101, 100)
        with self.assertRaises(ValueError):
            wilson(0, 0)
        with self.assertRaises(ValueError):
            evaluate({"winner_hit": 10}, 100)


if __name__ == "__main__":
    unittest.main()
