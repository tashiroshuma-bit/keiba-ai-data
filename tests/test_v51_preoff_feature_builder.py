import unittest
from scripts.v51_preoff_feature_builder import build,day_bias
ASOF="2026-11-14T09:00:00+09:00"
OFF="2026-11-14T10:00:00+09:00"
OLD_OFF="2026-11-01T10:00:00+09:00"
OLD_OBS="2026-11-01T11:00:00+09:00"

def runners():
    return [{"number":n,"horse_id":None,"jockey_id":str(n),
             "identity_evidence":None,"age_years":3} for n in (1,2,3)]
def run(rs,older=()):
    return build(rs,asof=ASOF,off=OFF,track="Tokyo",
                 surface="turf",distance_m=1600,class_index=2,
                 prior_day_results=older)

class V51FeatureBuilderTests(unittest.TestCase):
    def test_identity_missing_remains_missing(self):
        result=run(runners())
        self.assertEqual(result["identity_coverage"]["missing_ids"],3)
        self.assertIsNone(result["runners"][0]["horse_form_recent3"])
        self.assertIsNone(result["runners"][0]["relative_recent_form"])
        self.assertFalse(result["model_fit_complete"])

    def test_verified_history_and_opponents(self):
        r=runners()
        p={"horse_number":1,"horse_id":"jra:1",
           "source_url":"https://www.jra.go.jp/test","source_sha256":"a"*64,
           "observed_at":ASOF}
        r[0]["horse_id"]="jra:1";r[0]["identity_evidence"]=p
        h={"horse_id":"jra:1","off_at":OLD_OFF,"observed_at":OLD_OBS,
           "source_url":"https://www.jra.go.jp/test","source_sha256":"b"*64,
           "field_size":12,"finish_order":2,"class_index":1,
           "opponent_strength":0.7}
        r[0]["horse_history"]=[h]
        r[0]["body_weight_kg"]=480
        r[0]["body_weight_change_kg"]=6
        r[0]["weight_observed_at"]=ASOF
        ans=run(r)
        f=ans["runners"][0]
        self.assertEqual(f["horse_form_starts"],1)
        self.assertEqual(f["class_change"],1)
        self.assertAlmostEqual(f["horse_form_recent3"],10/11)
        self.assertAlmostEqual(f["bodyweight_change_percent"],100*6/474)
        self.assertIsNone(f["relative_recent_form"])

    def test_reject_future_histories(self):
        r=runners()
        r[0]["horse_id"]="jra:1"
        r[0]["identity_evidence"]={"horse_number":1,"horse_id":"jra:1",
           "source_url":"https://www.jra.go.jp/test","source_sha256":"a"*64,
           "observed_at":ASOF}
        r[0]["horse_history"]=[{"horse_id":"jra:1","off_at":OLD_OFF,
           "observed_at":"2026-11-14T09:01:00+09:00",
           "source_url":"https://www.jra.go.jp/test","source_sha256":"a"*64,
           "field_size":12,"finish_order":2}]
        with self.assertRaises(ValueError):run(r)

    def test_no_same_day_lookahead(self):
        today=[{"off_at":"2026-11-14T10:05:00+09:00",
                "observed_at":ASOF,"track":"Tokyo","surface":"turf",
                "horses":[{"field_size":10,"finish_order":1}]}]
        with self.assertRaises(ValueError):run(runners(),today)

    def test_completed_prior_race(self):
        earlier=[{"off_at":"2026-11-14T08:00:00+09:00",
                  "observed_at":"2026-11-14T08:10:00+09:00",
                  "track":"Tokyo","surface":"turf",
                  "horses":[{"field_size":9,"finish_order":1,"corner4_position":1,"gate_number":1},
                            {"field_size":9,"finish_order":8,"corner4_position":8,"gate_number":8}]}]
        ans=run(runners(),earlier)
        self.assertIsNotNone(ans["day_bias"]["pace_advantage"])
        self.assertGreater(ans["day_bias"]["pace_advantage"],0)

if __name__=="__main__":unittest.main()
