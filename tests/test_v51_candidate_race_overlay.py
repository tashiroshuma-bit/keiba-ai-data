import unittest
from pathlib import Path
from scripts.v51_candidate_race_overlay import overlay
ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/"operations/prediction_policy/v51_candidate_fitted_research.json"

class V51ShadowProjectionTests(unittest.TestCase):
    def setUp(self):
        self.base={"horses":[{"number":k+1,"name":"馬"+str(k+1),"p1":p}
            for k,p in enumerate((.5,.3,.2))]}
        self.source={"race_id":"202611080111","race_off_at":"2026-11-08T11:00:00+09:00",
           "forecast_asof":"2026-11-08T08:00:00+09:00","horses":[]}
        for h in self.base["horses"]:
            self.source["horses"].append({
                "number":h["number"],"horse_id":"jra:20201234"+str(h["number"]),
                "feature_values":[0.0]*34,
                "feature_evidence":{"source_url":"https://www.jra.go.jp/datafile/old.pdf",
                    "source_sha256":"a"*64,"off_at":"2026-11-01T11:00:00+09:00",
                    "published_at":"2026-11-02T10:00:00+09:00",
                    "observed_at":"2026-11-02T11:00:00+09:00"},
                "official_identity_proof":{
                    "race_id":self.source["race_id"],"horse_number":h["number"],
                    "horse_name":h["name"],"horse_id":"jra:20201234"+str(h["number"]),
                    "source_url":"https://www.jra.go.jp/JRADB/accessS.html",
                    "source_sha256":"b"*64,"observed_at":"2026-11-04T00:00:00+09:00"}})
    def test_research_zero_alpha_preserves_v50(self):
        r=overlay(self.base,self.source,MODEL,research_alpha=0)
        self.assertFalse(r["production_promotion"])
        self.assertTrue(r["v50_original_unchanged"])
        self.assertEqual({x["number"]:x["shadow_ensemble_p1"] for x in r["rankings"]},
                         {1:.5,2:.3,3:.2})
        self.assertAlmostEqual(sum(x["v51_candidate_p1"] for x in r["rankings"]),1)
    def test_bad_horse_number_or_identity_fails(self):
        self.source["horses"][0]["official_identity_proof"]["horse_number"]=8
        with self.assertRaises(ValueError):
            overlay(self.base,self.source,MODEL)
    def test_future_identity_proof_forbidden(self):
        self.source["horses"][1]["official_identity_proof"]["observed_at"]="2026-11-09T00:00:00+09:00"
        with self.assertRaises(ValueError):
            overlay(self.base,self.source,MODEL)
    def test_future_historical_result_forbidden(self):
        self.source["horses"][1]["feature_evidence"]["published_at"]="2026-11-09T00:00:00+09:00"
        with self.assertRaises(ValueError):
            overlay(self.base,self.source,MODEL)
    def test_incomplete_features_fails(self):
        self.source["horses"][0]["feature_values"]=[0]*5
        with self.assertRaises(ValueError):
            overlay(self.base,self.source,MODEL)
if __name__=="__main__":
    unittest.main()
