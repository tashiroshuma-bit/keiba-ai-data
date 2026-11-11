"""Tests for retrospective V51 extended feature timeline and parser."""
import unittest
import numpy as np
from scripts.v51_four_axis_historical_features import (
    _parse_corner,_parse_reported_weight,build_features,
    align_with_original,FEATURE_NAMES
)

def racer(rid,date,num,horse,jockey,rank):
    return {"race":rid,"date":date,"num":num,
       "horse_id":horse,"jockey_id":jockey,"rank":rank,
       "track":"Tokyo","surface":"turf","dist":1600}

class V51HistoricalExtraFeatures(unittest.TestCase):
    def test_canonical_reported_weight_and_corner_parsing(self):
        self.assertEqual(_parse_corner({"corner4_position":2},12),2)
        self.assertEqual(_parse_corner({"passing_positions":"6-5-3"},12),3)
        self.assertIsNone(_parse_corner({"finish_order":1},12))
        self.assertIsNone(_parse_corner({"passing_positions":"unverified"},12))
        self.assertAlmostEqual(_parse_reported_weight({
            "body_weight_raw":"480","body_weight_change_raw":"+8"}),100*8/472)
        self.assertIsNone(_parse_reported_weight({
            "body_weight_raw":"不明","body_weight_change_raw":"±0"}))

    def test_future_and_next_day_unpublished_results_not_used(self):
        a=[racer("A","2025-01-04",1,"jra:h1","jra:j1",1),
           racer("A","2025-01-04",2,"jra:h2","jra:j2",3),
           racer("A","2025-01-04",3,"jra:h3","jra:j3",2)]
        b=[racer("B","2025-01-05",1,"jra:h1","jra:j1",2),
           racer("B","2025-01-05",2,"jra:h4","jra:j4",1),
           racer("B","2025-01-05",3,"jra:h5","jra:j5",3)]
        c=[racer("C","2025-01-06",1,"jra:h1","jra:j1",3),
           racer("C","2025-01-06",2,"jra:h4","jra:j4",1),
           racer("C","2025-01-06",3,"jra:h2","jra:j2",2)]
        races={"A":a,"B":b,"C":c}
        source={("A",1):{"class_level":3,"corner4":2,
               "previous_weight_delta_pct":1.5},
                ("A",2):{"class_level":3,"corner4":9,
               "previous_weight_delta_pct":-1.2}}
        x,cov=build_features(races,source,minimum_days=2)
        self.assertEqual(len(x),9)
        self.assertEqual(cov["feature_rows"],9)
        self.assertEqual(x[("A",1)][2],1.) # class missing
        self.assertEqual(x[("B",1)][2],1.) # previous day not published by stable cutoff
        self.assertEqual(x[("B",1)][7],1.) # corner cannot leak
        self.assertEqual(x[("C",1)][2],0.) # day-2 class available
        self.assertEqual(x[("C",1)][7],0.) # day-2 passing position available
        self.assertEqual(x[("C",1)][13],0.) # day-2 reported weight delta available
        self.assertGreater(x[("C",1)][8],0) # prior jockey success effect
        self.assertEqual(x[("C",1)][4],1/2)
        arr=align_with_original(x,["A","C"],[1,1])
        self.assertEqual(arr.shape,(2,len(FEATURE_NAMES)))
        self.assertTrue(np.isfinite(arr).all())
        with self.assertRaisesRegex(ValueError,"embargo"):
            build_features(races,source,minimum_days=1)
        with self.assertRaisesRegex(ValueError,"alignment"):
            align_with_original(x,["UNSEEN"],[1])

if __name__=="__main__":
    unittest.main()
