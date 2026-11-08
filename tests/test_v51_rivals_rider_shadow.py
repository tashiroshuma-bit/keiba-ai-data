import unittest
import datetime as dt
import numpy as np
from scripts.retrain_v51_rivals_rider_shadow import make_enriched, ADDITIONS
from scripts import retrain_v50_canonical_db_shadow as base

def fixture(date,race_id,winner=0):
    field=[]
    for k in range(3):
        field.append({"horse_id":"jra:h"+str(k),"jockey_id":"jra:j"+str(k),
          "finish":1+((k-winner)%3),"speed_z":.1*k,"corner4":k+1})
    event={"date":date,"race_id":race_id,"surface":"turf","field":3,"horses":field}
    row={"date":date,"race_id":race_id,"winner":winner,
         "X":np.zeros((3,25),dtype=float)}
    return event,row

class V51RivalHorseAsOfTest(unittest.TestCase):
    def test_2day_history_cutoff_and_future_outcome_exclusion(self):
        e1,r1=fixture("2025-01-01","race1",winner=0)
        e2,r2=fixture("2025-01-02","race2",winner=1)
        e3,r3=fixture("2025-01-03","race3",winner=2)
        a=make_enriched([e1,e2,e3],[r1,r2,r3])
        self.assertEqual(r1["X"].shape,(3,34))
        self.assertTrue(np.allclose(r1["X"][:,25:34],0,atol=1e-12))
        self.assertTrue(np.allclose(r2["X"][:,25:34],0,atol=1e-12))
        self.assertTrue(np.isfinite(r3["X"]).all())
        self.assertEqual(a["opponent_history_available"],3)
        self.assertEqual(a["rider_surface_available"],3)
    def test_unlinked_horses_not_assigned_implicit_identity(self):
        e1,r1=fixture("2025-01-01","race1")
        e2,r2=fixture("2025-01-03","race2")
        e1["horses"][0]["horse_id"]=None
        e2["horses"][0]["horse_id"]=None
        stats=make_enriched([e1,e2],[r1,r2])
        self.assertEqual(stats["opponent_history_available"],2)
        self.assertEqual(r2["X"].shape,(3,34))
    def test_model_mutation_is_not_global_version_update(self):
        self.assertEqual(len(ADDITIONS),9)
        self.assertEqual(len(base.FEATURES),25)
    def test_race_alignment_fail_closed(self):
        e,r=fixture("2025-01-01","r1")
        with self.assertRaises(ValueError):
            make_enriched([e],[{**r,"race_id":"wrong"}])

if __name__=="__main__":
    unittest.main()
