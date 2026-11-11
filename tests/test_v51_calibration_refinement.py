import unittest
import numpy as np
from scripts.v51_calibration_refinement import select, candidate, metrics
from scripts.v51_recovered_id_conditional_rank import softmax

class V51CalibrationRefinement(unittest.TestCase):
    def test_positive_temperature_does_not_reorder_winners(self):
        z=np.array([1.3,0.9,2.2,-0.8])
        winner=int(np.argmax(z))
        for t in (0.6,0.9,1.,1.6,2.5):
            self.assertEqual(int(np.argmax(softmax(z,t))),winner)
            self.assertAlmostEqual(float(softmax(z,t).sum()),1.)
    def test_selection_uses_only_supplied_2025_cv_metrics(self):
        base={"winner_logloss":2.25,"winner_brier":.87,
              "ece_confidence":.031,"conditional_second_logloss":2.4,
              "conditional_third_logloss":2.5}
        good={**base,"winner_logloss":2.23,"winner_brier":.86,"ece_confidence":.028}
        overfit={**base,"winner_logloss":2.1,"winner_brier":.92,"ece_confidence":.07}
        self.assertEqual(select({"global":base,"original-strata":good,
                                 "half-shrunk-strata":overfit}),"original-strata")
    def test_no_candidate_beating_guard_returns_global(self):
        base={"winner_logloss":2.2,"winner_brier":.87,"ece_confidence":.03,
              "conditional_second_logloss":2.3,"conditional_third_logloss":2.4}
        bad={**base,"winner_logloss":2.1,"winner_brier":.95}
        self.assertEqual(select({"global":base,"original-strata":bad}),"global")

if __name__=="__main__":unittest.main()
