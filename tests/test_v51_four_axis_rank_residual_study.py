"""Synthetic optimization tests, NOT a measured increase in real-race accuracy."""
import unittest
import numpy as np
from scripts.v51_four_axis_rank_residual_study import (
    fit_residual,normalize_by_training,candidates_for_training,select_candidate
)

class V51FourAxisRankResidual(unittest.TestCase):
    def test_additive_rank_learns_strictly_from_supplied_training_groups(self):
        n_races=25
        n=4*n_races
        base=np.zeros(n,float)
        X=np.zeros((n,2),float)
        groups=[]
        for race in range(n_races):
            starts=np.arange(4*race,4*race+4)
            # Winner #3 is predictable only from a new feature.
            X[starts,0]=[-1.,-.5,0.,1.]
            X[starts,1]=[0.,1.,0.,-1.]
            groups.append({"indices":starts,"first":int(starts[-1])})
        w,diag=fit_residual(base,X,groups,.03,maxiter=100)
        self.assertEqual(w.shape,(2,))
        self.assertGreater(w[0],0.1)
        self.assertGreaterEqual(diag["train_races"],n_races)
        self.assertEqual(diag["runners"],n)
        # Frozen baseline logits remain unchanged.
        self.assertTrue(np.array_equal(base,np.zeros(n)))

    def test_only_real_observed_feature_groups_selected(self):
        X=np.zeros((100,14))
        for pos in (2,3,7,10,13):X[:,pos]=1
        tr=np.arange(100)
        self.assertEqual(candidates_for_training(X,tr),{})
        X[:,7]=0
        X[:,4]=np.linspace(0,1,100)
        can=candidates_for_training(X,tr)
        self.assertIn("running_style",can)
        self.assertIn("combined",can)
        self.assertNotIn("previous_weight",can)
        self.assertNotIn("opponent_class",can)

    def test_nan_or_empty_input_denied(self):
        with self.assertRaisesRegex(ValueError,"ridge"):
            fit_residual(np.zeros(4),np.ones((4,2)),
                        [{"indices":np.arange(4),"first":3}],0)
        with self.assertRaisesRegex(ValueError,"no prior"):
            fit_residual(np.zeros(4),np.ones((4,2)),[],.03)
        x=np.ones((6,2))
        norm,mean,scale=normalize_by_training(x,np.arange(3))
        self.assertTrue(np.isfinite(norm).all())
        self.assertTrue(np.all(scale==1))

    def test_validation_selection_predeclared_guard(self):
        base={"top1_accuracy":.25,"winner_logloss":2.2,
              "winner_brier":.86,"ece_confidence":.025}
        good={**base,"top1_accuracy":.27,"winner_logloss":2.19}
        bad={**base,"top1_accuracy":.4,"winner_logloss":2.5}
        self.assertEqual(select_candidate({"official_baseline":base,
            "jockey_condition":good,"overfitted":bad}),
            "jockey_condition")

if __name__=="__main__":
    unittest.main()
