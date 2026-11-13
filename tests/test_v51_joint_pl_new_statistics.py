"""Rank-model correctness tests. Synthetic ONLY; not actual 2025 precision."""
import unittest
import numpy as np
from scripts.v51_joint_pl_new_statistics import (
    _samples,_recency_weights,design_matrix,joint_stage_fit,race_score_records,
)
from scripts.jra_historical_horse_id_ablation import FEATURES
from scripts.v51_four_axis_historical_features import FEATURE_NAMES

class JointPLNewStatistics(unittest.TestCase):
    def toy(self,n=80,seed=20261114):
        rng=np.random.default_rng(seed)
        X=rng.normal(size=(n*5,3))
        groups=[]
        for j in range(n):
            inds=np.arange(5*j,5*j+5)
            # Historical podium generated from prior covariate signal; no labels in X
            order=inds[np.argsort(-X[inds,0])]
            groups.append({"indices":inds,"first":int(order[0]),
                "second":int(order[1]),"third":int(order[2]),
                "date":f"2024-{1+j//31:02d}-{1+j%31:02d}",
                "podium_valid":True})
        return X,groups

    def test_conditional_stage_removes_finished_horses(self):
        X,g=self.toy(10)
        s1=_samples(g,1);s2=_samples(g,2);s3=_samples(g,3)
        self.assertEqual((len(s1),len(s2),len(s3)),(10,10,10))
        for a,b,c in zip(s1,s2,s3):
            self.assertEqual(len(a[0]),5)
            self.assertEqual(len(b[0]),4)
            self.assertEqual(len(c[0]),3)
            self.assertNotIn(g[0]["first"],s2[0][0])
            self.assertNotIn(g[0]["second"],s3[0][0])

    def test_joint_pl_fit_learns_three_stage_scores(self):
        X,g=self.toy()
        fit,meta=joint_stage_fit(X,g,ridge=.06,coupling=.12,
                             half_life_days=365,maxiter=250)
        self.assertEqual(fit.shape,(3,3))
        self.assertGreater(fit[0,0],.1)
        self.assertGreater(fit[1,0],.1)
        self.assertGreater(fit[2,0],.1)
        records=race_score_records(X,g,fit)
        self.assertEqual(len(records),len(g))
        self.assertEqual(len(records[0][0]),3)
        for logits,gg in records:
            self.assertEqual([len(z) for z in logits],[5,5,5])
        self.assertGreater(meta["train_first_races"],0)
        self.assertFalse(meta["outcome_labels_used_in_prediction_inputs"])

    def test_recent_race_gets_more_weight(self):
        w=_recency_weights(["2023-01-01","2024-01-01","2024-12-01"],365)
        self.assertLess(w[0],w[1])
        self.assertLess(w[1],w[2])
        self.assertAlmostEqual(w.mean(),1)
        with self.assertRaisesRegex(ValueError,"half-life"):
            _recency_weights(["2024-01-01"],1)

    def test_nonlinear_basis_only_prior_fields_and_fixed_training_normalizers(self):
        rng=np.random.default_rng(12)
        original=rng.normal(size=(48,len(FEATURES)))
        extra=rng.normal(size=(48,len(FEATURE_NAMES)))
        tr=np.arange(32)
        Xt,rec=design_matrix(original,extra,FEATURES,FEATURE_NAMES,tr)
        self.assertEqual(Xt.shape[0],48)
        self.assertGreater(Xt.shape[1],45)
        self.assertTrue(np.isfinite(Xt).all())
        self.assertEqual(rec["train_rows"],len(tr))
        self.assertFalse(rec["feature_selection_used_labels"])
        self.assertEqual(len(rec["basis_names"]),Xt.shape[1])
        self.assertTrue(all("result" not in x for x in rec["basis_names"]))
        # Deliberately change only the heldout covariates: train transformation
        # and fitted train-only moments must not change.
        changed=original.copy()
        changed[tr[-1]+1:]+=800
        Xt2,rec2=design_matrix(changed,extra,FEATURES,FEATURE_NAMES,tr)
        self.assertTrue(np.allclose(Xt[tr],Xt2[tr]))
        self.assertEqual(rec["raw_feature_mean"],rec2["raw_feature_mean"])

    def test_refuse_invalid_labels_and_features(self):
        X,g=self.toy(2)
        bad=dict(g[0]);bad["second"]=bad["first"];groups=[bad,g[1]]
        with self.assertRaisesRegex(ValueError,"conditional"):
            joint_stage_fit(X,groups)
        with self.assertRaisesRegex(ValueError,"finite"):
            xx=X.copy();xx[0,0]=np.nan;joint_stage_fit(xx,g)
        with self.assertRaisesRegex(ValueError,"invalid ridge"):
            joint_stage_fit(X,g,ridge=-1)
        with self.assertRaisesRegex(ValueError,"coefficient shape"):
            race_score_records(X,g,np.ones((2,3)))

if __name__=="__main__":
    unittest.main()
