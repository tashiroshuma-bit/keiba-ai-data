import unittest
from collections import defaultdict
from scripts.jra_historical_horse_id_ablation import HistoricalStats, FEATURES, create_feature_rows
from scripts.v51_frozen_live_feature_builder import compute_one

class FrozenFeatureTests(unittest.TestCase):
    def test_current_race_result_is_rejected_by_production_guard(self):
        import datetime as dt
        from scripts.standard_v51_forecast import evidence_guard
        cutoff=dt.datetime(2026,11,15,9,tzinfo=dt.timezone(dt.timedelta(hours=9)))
        off=dt.datetime(2026,11,15,15,40,tzinfo=dt.timezone(dt.timedelta(hours=9)))
        h={"number":1,"horse_id":"jra:1234567890","prior_starts":2,
           "latest_history_date":"2026-11-15",
           "historical_availability_basis":"prior_calendar_date_verified_result",
           "official_identity_proof":{"horse_id":"jra:1234567890","horse_number":1,
              "source_url":"https://sp.jra.jp/JRADB/accessD.html",
              "source_sha256":"a"*64,"observed_at":cutoff.isoformat()},
           "features_observed_at":cutoff.isoformat()}
        with self.assertRaisesRegex(ValueError,"lookahead"):
            evidence_guard(h,cutoff,off)
        h["latest_history_date"]="2026-11-14"
        evidence_guard(h,cutoff,off)

    def test_nonempty_historical_state_matches_original_generator(self):
        from scripts.jra_historical_horse_id_ablation import strength
        base=[]
        for n in range(1,4):
            base.append({"race":"prior","date":"2026-11-13","num":n,"rank":n,
                         "horse_id":"jra:h"+str(n),"jockey_id":"jra:j"+str(n),
                         "age":4,"female":1,"weight":56.0,"gate":n,
                         "track":"京都","surface":"turf","dist":2200,
                         "status":"validated_result"})
        later=[dict(r,race="next",date="2026-11-14") for r in base]
        expected,*_=create_feature_rows({"prior":base,"next":later},"full")
        horses=defaultdict(HistoricalStats)
        jockeys=defaultdict(HistoricalStats)
        for r in base:
            quality=strength(r["rank"],3)
            horses[r["horse_id"]].update(r,quality)
            jockeys[r["jockey_id"]].update(r,quality)
        live=[{"number":r["num"],"horse_id":r["horse_id"],"jockey_id":r["jockey_id"],
               "age":r["age"],"female":r["female"],"carried_weight":r["weight"],"gate":r["gate"]}
              for r in later]
        got=compute_one(live,horses,jockeys,"2026-11-14","京都","turf",2200)
        for a,b in zip(got,expected[3:]):
            for x,y in zip(a,b):
                self.assertAlmostEqual(x,float(y),places=6)

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
