"""Unit checks only. Real 2025 cohort is deliberately not fabricated."""
import unittest
import numpy as np
from scripts.v51_2025_winner_stage_refit_study import fit_one
from scripts.v51_2025_coefficient_calibration_grid import (
    GROUPS, FACTORS, make_splits, scale_stage1, coefficient_choice,
    bootstrap_paired_hits, winner_by_date
)

class V51CoefficientGrid(unittest.TestCase):
    def test_nonoverlapping_groups_and_not_bodyweight(self):
        allcols=[c for cols in GROUPS.values() for c in cols]
        self.assertEqual(len(set(allcols)),len(allcols))
        self.assertTrue(all(0<=n<31 for n in allcols))
        self.assertNotIn("bodyweight",GROUPS)

    def test_group_scale_changes_only_first_stage(self):
        weights=np.ones((3,31),float)
        test=scale_stage1(weights,"recent_form",0.5)
        self.assertTrue(np.all(test[1:]==1))
        self.assertTrue(np.all(test[0,list(GROUPS["recent_form"])]==0.5))
        untouched=[x for x in range(31) if x not in GROUPS["recent_form"]]
        self.assertTrue(np.all(test[0,untouched]==1))
        self.assertTrue(np.all(weights==1))
        with self.assertRaisesRegex(ValueError,"out-of-grid"):
            scale_stage1(weights,"jockey_history",100.0)

    def test_only_2025_calendar_dates_enter_search(self):
        gs=[]
        for year in (2024,2025,2026):
            for d in range(1,81):
                for k in range(30):
                    gs.append({"date":f"{year}-01-{d:02d}", "race":f"{year}-{d}-{k}",
                     "year":year,"status":"validated_result"})
        fit,search,confirm,meta=make_splits(gs)
        self.assertTrue(all(x["year"]==2025 for x in fit+search+confirm))
        self.assertEqual(len(fit)+len(search)+len(confirm),2400)
        self.assertFalse(set(x["date"] for x in fit)&set(x["date"] for x in search))
        self.assertFalse(set(x["date"] for x in search)&set(x["date"] for x in confirm))

    def test_coefficient_selection_scores_hits_not_temperature(self):
        base={"top1_accuracy":.25,"winner_logloss":2.25,"winner_brier":.87,
              "ece_confidence":.03}
        improve={**base,"top1_accuracy":.27,"winner_logloss":2.24}
        overfit={**base,"top1_accuracy":.40,"winner_logloss":2.8}
        self.assertEqual(coefficient_choice(
            {"original":base,"recent_form__x1.25":improve,
             "recent_form__x1.5":overfit},base),"recent_form__x1.25")

    def test_real_optimizer_winner_stage_refit_without_2025_data(self):
        rng=np.random.default_rng(5)
        X=rng.normal(size=(60,31))
        groups=[]
        for i in range(15):
            indexes=np.array([i*4+j for j in range(4)])
            groups.append({"indices":indexes,"first":int(indexes[0]),
                "second":int(indexes[1]),"third":int(indexes[2]),
                "podium_valid":True})
        base=np.zeros((3,31),dtype=float)
        w,diag=fit_one(X,groups,base,drop="jockey_history",ridge=0.1,maxiter=40)
        self.assertEqual(w.shape,(3,31))
        self.assertTrue(np.all(w[0,list(GROUPS["jockey_history"])]==0))
        self.assertTrue(np.all(w[1:]==0))
        self.assertEqual(diag["race_sets"],15)
        with self.assertRaisesRegex(ValueError,"ridge must"):
            fit_one(X,groups,base,ridge=0)

    def test_identical_heldout_predictions_have_zero_day_bootstrap_gain(self):
        rec=[]
        for d in range(1,11):
            g={"date":f"2025-10-{d:02d}","indices":np.array([0,1,2]),"first":0}
            z=[np.array([1.3,.7,0.]),np.array([0.,1.,2.]),np.array([0.,1.,2.])]
            rec.append((z,g))
        cal={"winner_entropy_confidence_groups":{
             a+"__"+b:{"temp":1.}
             for a in ("high_entropy","other_entropy")
             for b in ("close_field","clear_favorite")}}
        got=bootstrap_paired_hits((rec,cal),(rec,cal),repetitions=20)
        self.assertEqual(got["hit_rate_delta"],0.)
        self.assertEqual(got["paired_date_bootstrap95"],[0.,0.])

if __name__=="__main__":
    unittest.main()
