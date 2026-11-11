"""Scoring integration for full-period four-axis study; synthetic, not 2025."""
import unittest

import numpy as np
from scripts.v51_four_axis_rank_residual_study import (
    podium_exact_metrics, coverage_by_year
)

CAL={
 "global_stage_temperatures":{"1":1.0,"2":1.0,"3":1.0},
 "winner_entropy_confidence_groups":{
   e+"__"+f:{"temp":1.0} for e in
      ("high_entropy","other_entropy") for f in ("clear_favorite","close_field")
 },
 "group_entropy_cutoff":0.94,
 "group_favorite_cutoff":0.25
}

class FourAxisFullScoreIntegrity(unittest.TestCase):
    def test_exact_ordered_and_unordered_podium(self):
        g={"indices":np.array([5,6,7],dtype=int),"first":5,
           "second":6,"third":7,"podium_valid":True}
        score=[
            np.array([4.,2.,0.]),
            np.array([0.,4.,1.]),
            np.array([0.,1.,4.])
        ]
        got=podium_exact_metrics([(score,g)],CAL)
        self.assertEqual(got["valid_unique_podium_races"],1)
        self.assertEqual(got["ordered_exact_hits"],1)
        self.assertEqual(got["unordered_exact_hits"],1)
        self.assertEqual(got["ordered_exact_rate"],1.0)

    def test_exclude_invalid_podium_from_true_denominator(self):
        g={"indices":np.array([1,2,3],dtype=int),
           "first":1,"second":None,"third":None,
           "podium_valid":False}
        row=[np.zeros(3),np.zeros(3),np.zeros(3)]
        got=podium_exact_metrics([(row,g)],CAL)
        self.assertEqual(got["valid_unique_podium_races"],0)
        self.assertIsNone(got["ordered_exact_rate"])

    def test_yearwise_actual_observation_flags(self):
        # Indices 2,3,7,10,13: 0 means historical source feature observed.
        data=np.ones((3,14))
        data[0,2]=0
        data[1,3]=0
        data[1,7]=0
        data[2,10]=0
        data[2,13]=0
        years=np.array([2023,2025,2025],dtype=int)
        c=coverage_by_year(data,years)
        self.assertEqual(c["2023"]["past_class_observed"],1)
        self.assertEqual(c["2025"]["past_rival_strength_observed"],1)
        self.assertEqual(c["2025"]["past_corner_style_observed"],1)
        self.assertEqual(c["2025"]["jockey_condition_observed"],1)
        self.assertEqual(c["2025"]["past_weight_delta_observed"],1)
        self.assertEqual(c["2025"]["runners"],2)

if __name__=="__main__":
    unittest.main()
