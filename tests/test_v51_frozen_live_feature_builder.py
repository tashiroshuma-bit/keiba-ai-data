import unittest
from collections import defaultdict
from scripts.jra_historical_horse_id_ablation import HistoricalStats, FEATURES, create_feature_rows
from scripts.v51_frozen_live_feature_builder import compute_one

class FrozenFeatureTests(unittest.TestCase):
    def test_31_features_match_original_historical_generator(self):
        # First historical race has no prior results; same field and same
        # formulas must exactly match original frozen training feature vector.
        rows=[]
        for n in range(1,4):
            rows.append({"race":"test","date":"2026-11-14","num":n,"rank":n,
                         "horse_id":"jra:h"+str(n),"jockey_id":"jra:j"+str(n),
                         "age":4,"female":1,"weight":56.0,"gate":n,
                         "track":"京都","surface":"turf","dist":2200,
                         "status":"validated_result"})
        expected,*_=create_feature_rows({"test":rows},"full")
        current=[{"number":r["num"],"horse_id":r["horse_id"],"jockey_id":r["jockey_id"],
                  "age":r["age"],"female":r["female"],"carried_weight":r["weight"],"gate":r["gate"]}
                 for r in rows]
        got=compute_one(current,defaultdict(HistoricalStats),defaultdict(HistoricalStats),
                        "2026-11-14","京都","turf",2200)
        self.assertEqual(len(got),3)
        self.assertEqual(len(got[0]),31)
        for a,b in zip(got,expected):
            for x,y in zip(a,b):
                self.assertAlmostEqual(x,float(y),places=6)
        self.assertEqual(len(FEATURES),31)

if __name__=="__main__":
    unittest.main()
