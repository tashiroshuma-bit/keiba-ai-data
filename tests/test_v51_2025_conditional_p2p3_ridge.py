import unittest
import numpy as np
from scripts.v51_2025_conditional_p2p3_ridge import (
    candidates,choose,fit_stages,podium_result,calibration_on_early_2025
)

class V51ConditionalP2P3RankRidge(unittest.TestCase):
    def test_only_p2_and_p3_coefficients_change(self):
        rng=np.random.default_rng(11)
        x=rng.normal(size=(100,31))
        groups=[]
        for i in range(25):
            indexes=np.array([4*i+j for j in range(4)],dtype=int)
            groups.append({"indices":indexes,"first":int(indexes[0]),
              "second":int(indexes[1]),"third":int(indexes[2]),
              "podium_valid":True,"date":"2025-01-01","year":2025,
              "status":"validated_result","race":str(i)})
        original=np.zeros((3,31),float)
        original[0,0]=.3
        w,audit=fit_stages(x,groups,original,.03,.03)
        self.assertTrue(np.array_equal(w[0],original[0]))
        self.assertTrue(np.array_equal(original[1:],np.zeros((2,31))))
        self.assertEqual(audit["second"]["race_sets"],25)
        self.assertEqual(audit["third"]["race_sets"],25)

    def test_candidate_count_and_no_2026_selector(self):
        self.assertEqual(len(candidates()),10)
        base={"second_conditional_logloss":2.0,
              "third_conditional_logloss":1.8,
              "combined_conditional_logloss":3.8}
        good={**base,"second_conditional_logloss":1.96,
               "third_conditional_logloss":1.78,
               "combined_conditional_logloss":3.74}
        invalid={**base,"second_conditional_logloss":1.70,
                  "third_conditional_logloss":1.95,
                  "combined_conditional_logloss":3.65}
        self.assertEqual(choose({"original":base,"safe":good,"bad":invalid}),"safe")

    def test_research_stage_joint_mass_normalization(self):
        from scripts.v51_recovered_id_conditional_rank import make_race_probabilities
        c={"group_entropy_cutoff":.94,"group_favorite_cutoff":.25,
           "global_stage_temperatures":{"1":1.0,"2":1.0,"3":1.0},
           "winner_entropy_confidence_groups":{
              a+"__"+b:{"temp":1.}
              for a in ("high_entropy","other_entropy")
              for b in ("close_field","clear_favorite")}}
        z=[np.array([2.0,1.0,.5]),np.array([0.,1.,2.]),np.array([1.,0.,2.])]
        got=make_race_probabilities(z,c)
        self.assertAlmostEqual(got["joint_normalization"],1.)
        self.assertEqual(len(got["ordered_pick"]),3)
        self.assertAlmostEqual(sum(got[key].sum() for key in ("p1","p2","p3")),3.)
if __name__=="__main__":unittest.main()
