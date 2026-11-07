"""Protect time-safe v50 preoff odds adjustment from hindsight and roster leaks."""
import unittest
from scripts.v50_preoff_odds_blend import combine

class MarketOddsBlendTests(unittest.TestCase):
    def setUp(self):
        self.model={"horses":[{"number":1,"p1":0.5},{"number":2,"p1":0.3},
                              {"number":3,"p1":0.2}]}
        self.snap={"phase":"preoff","source_kind":"observed_public_win_odds",
                   "observed_at":"2026-11-08T08:00:00+09:00",
                   "horses":[{"number":1,"odds":2.2},{"number":2,"odds":5.5},
                             {"number":3,"odds":10.0}]}
        self.off="2026-11-08T12:00:00+09:00"
    def test_valid_market_probabilities_normalized(self):
        r=combine(self.model,self.snap,alpha=0.2,off_at=self.off)
        self.assertAlmostEqual(sum(h["blend_p1"] for h in r["ranking"]),1,places=10)
        self.assertEqual(r["ranking"][0]["number"],1)
        self.assertEqual(r["probability_calibration"],"UNVERIFIED_REQUIRES_CHRONOLOGICAL_HOLDOUT")
    def test_zero_alpha_preserves_model(self):
        r=combine(self.model,self.snap,alpha=0,off_at=self.off)
        ps={h["number"]:h["blend_p1"] for h in r["ranking"]}
        self.assertAlmostEqual(ps[1],0.5)
        self.assertAlmostEqual(ps[2],0.3)
    def test_full_alpha_reproduces_devig_market(self):
        r=combine(self.model,self.snap,alpha=1,off_at=self.off)
        self.assertAlmostEqual(r["ranking"][0]["blend_p1"],
                               r["ranking"][0]["market_p1_devig"])
    def test_forbid_race_start_or_later_odds(self):
        self.snap["observed_at"]=self.off
        with self.assertRaises(ValueError):combine(self.model,self.snap,alpha=0.2,off_at=self.off)
    def test_forbid_final_postrace_market(self):
        self.snap["phase"]="final"
        with self.assertRaises(ValueError):combine(self.model,self.snap,alpha=0.2,off_at=self.off)
    def test_forbid_invalid_roster(self):
        self.snap["horses"][-1]["number"]=4
        with self.assertRaises(ValueError):combine(self.model,self.snap,alpha=0.2,off_at=self.off)
    def test_forbid_incomplete_odds(self):
        self.snap["horses"][-1]["odds"]=None
        with self.assertRaises(ValueError):combine(self.model,self.snap,alpha=0.2,off_at=self.off)
    def test_forbid_invalid_mix(self):
        with self.assertRaises(ValueError):combine(self.model,self.snap,alpha=1.2,off_at=self.off)

if __name__=="__main__":unittest.main()
