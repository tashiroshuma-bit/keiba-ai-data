import math
import unittest

import numpy as np
import pandas as pd

from joint_top3_model import horse_key, ordered_scenarios, state_features, update_state


class JointTop3Test(unittest.TestCase):
    def test_exhaustive_probabilities(self):
        rows = ordered_scenarios([1, 2, 3, 4, 5], np.array([.2, -.5, 0, 1.1, .3]))
        self.assertEqual(len(rows), 60)
        self.assertAlmostEqual(sum(r["probability"] for r in rows), 1.)
        self.assertTrue(all(len(set(r["order"])) == 3 for r in rows))

    def test_same_race_outcome_never_enters_feature(self):
        row = pd.Series(dict(horse="架空馬", date=pd.Timestamp("2026-10-10"), age=2,
                             sex="牡", frame=2, number=3, course="東京",
                             surface="芝", distance=1600, finish_order=1))
        a = state_features(row, {}, 8)
        row["finish_order"] = 17
        b = state_features(row, {}, 8)
        np.testing.assert_allclose(a, b)
        self.assertEqual(horse_key(row), ("架空馬", 2024))

    def test_prior_race_is_available_only_at_later_date(self):
        past = pd.DataFrame([dict(horse="架空馬", date=pd.Timestamp("2026-10-01"), age=2,
                                  sex="牝", frame=1, number=1, course="東京", surface="芝",
                                  distance=1600, finish_order=1)])
        state = __import__("collections").defaultdict(list)
        update_state(state, past)
        future = past.iloc[0].copy()
        future["date"] = pd.Timestamp("2026-10-10")
        self.assertAlmostEqual(state_features(future, state, 8)[4], math.log(2))
        self.assertAlmostEqual(state_features(past.iloc[0], state, 8)[4], 0)


if __name__ == "__main__":
    unittest.main()

