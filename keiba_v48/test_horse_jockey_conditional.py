"""Research feature tests; no historical outcome leakage or false confidence."""
import unittest
from horse_jockey_conditional import horse_podium, jockey_residual, adjust_log_score


class HorseJockeyConditionalTest(unittest.TestCase):
    def test_zero_starts_returns_prior_and_zero_confidence(self):
        result=horse_podium(dict(starts=0,wins=0,seconds=0,thirds=0))
        self.assertAlmostEqual(result["value"],.15)
        self.assertEqual(result["confidence"],0)
        self.assertIsNone(result["raw"])

    def test_podium_weight_and_shrinkage(self):
        a=horse_podium(dict(starts=2,wins=1,seconds=1,thirds=0))
        b=horse_podium(dict(starts=20,wins=10,seconds=10,thirds=0))
        self.assertLess(a["confidence"],b["confidence"])
        self.assertLess(a["value"],b["value"])

    def test_invalid_career_rejected(self):
        with self.assertRaises(ValueError):
            horse_podium(dict(starts=1,wins=1,seconds=1,thirds=0))

    def test_no_rider_history_keeps_horse_only(self):
        runner=dict(starts=5,wins=1,seconds=1,thirds=1)
        self.assertEqual(adjust_log_score(.2,runner),
                         adjust_log_score(.2,runner,{}))


if __name__=="__main__":
    unittest.main()
