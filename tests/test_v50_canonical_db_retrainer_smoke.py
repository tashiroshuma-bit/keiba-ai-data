"""Smoke tests for canonical research-only retrainer; no private SQLite in CI."""
import unittest
import numpy as np
from scripts.retrain_v50_canonical_db_shadow import create_rows,score,FEATURES
from scripts.calibrate_v50_canonical_db_race_risk import fit_binary,prob_binary

def race(date,id,winner):
    horses=[{"num":i+1,"horse_id":f"jra:horse{i}","jockey_id":f"jra:rider{i}",
        "finish":(1 if i==winner else 2 if i==(winner+1)%3 else 3),
        "sex_age":"牡3鹿","gate":i+1,"speed_z":None,"corner4":None,"final_odds":None}
        for i in range(3)]
    return {"date":date,"race_id":id,"track":"東京","surface":"turf",
      "dist":1600,"field":3,"winner":winner,"horses":horses}

class CanonicalRetrainShadowTests(unittest.TestCase):
    def test_two_day_results_lag_not_same_day_leak(self):
        events=[race("2025-01-01","A",0),race("2025-01-02","B",1),
            race("2025-01-03","C",2)]
        features,_=create_rows(events)
        self.assertEqual(len(features),3)
        self.assertAlmostEqual(float(features[0]["X"][0,0]),0.)
        self.assertAlmostEqual(float(features[1]["X"][0,0]),0.)
        self.assertGreater(float(features[2]["X"][0,0]),0.)
    def test_padded_race_probability_and_hit(self):
        events=[race("2025-01-01","A",0),race("2025-01-02","B",1)]
        rows,_=create_rows(events)
        predictions=np.full((2,3),1/3)
        got=score(rows,predictions)
        self.assertEqual(got["n"],2)
        self.assertAlmostEqual(got["logloss"],float(-np.log(1/3)),places=5)
        self.assertEqual(len(FEATURES),25)
    def test_failure_classifier_is_finite(self):
        X=np.array([[.1,.2],[.3,.4],[.8,.2],[.9,.6],[.4,.5],[.1,.7]])
        Y=np.array([1,1,0,0,1,0])
        cls=fit_binary(X,Y)
        predicted=prob_binary(X,cls)
        self.assertTrue(np.isfinite(predicted).all())
        self.assertTrue(((predicted>0)&(predicted<1)).all())

if __name__=="__main__":unittest.main()
