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
    def test_market_favorite_risk_markers(self):
        r=combine(self.model,self.snap,alpha=0.20,off_at=self.off)
        m=r["market_structure"]
        self.assertEqual(m["favorite_number"],1)
        self.assertEqual(m["field_size"],3)
        self.assertAlmostEqual(m["favorite_vs_second_gap"],
                               m["favorite_market_probability"]-m["runnerup_market_probability"])
        self.assertEqual(m["interpretation"],"HISTORICAL_ASSOCIATIONS_NOT_CALIBRATED")
        self.assertNotIn("LARGE_FIELD_14_PLUS",m["risk_markers"])
    def test_full_field_tied_odds_flag(self):
        self.snap["horses"]=[{"number":1,"odds":5.0},
                            {"number":2,"odds":5.0},
                            {"number":3,"odds":8.0}]
        r=combine(self.model,self.snap,alpha=0.20,off_at=self.off)
        self.assertIn("CLOSE_TOP_TWO_GAP_UNDER_3PP",
                      r["market_structure"]["risk_markers"])

    def test_outsider_third_ranked_by_p3_not_win_probability(self):
        model={"horses":[
            {"number":1,"name":"A","p1":.5,"p2":.26,"p3":.15},
            {"number":2,"name":"B","p1":.27,"p2":.33,"p3":.30},
            {"number":3,"name":"C","p1":.15,"p2":.26,"p3":.32},
            {"number":4,"name":"D","p1":.08,"p2":.15,"p3":.23},
        ]}
        snapshot={"phase":"preoff","source_kind":"observed_public_win_odds",
            "observed_at":"2026-11-08T08:00:00+09:00",
            "horses":[{"number":1,"odds":2.1},{"number":2,"odds":4.0},
                     {"number":3,"odds":7.0},{"number":4,"odds":12.0}]}
        r=combine(model,snapshot,alpha=.2,off_at=self.off)
        self.assertEqual(len(r["outsider_third_candidates"]),1)
        candidate=r["outsider_third_candidates"][0]
        self.assertEqual(candidate["number"],4)
        self.assertEqual(candidate["market_rank_preoff"],4)
        self.assertEqual(candidate["popularity_band"],"4-6")
        ref=candidate["historical_2025_group_reference_not_horse_probability"]
        self.assertEqual(ref["sample"],1052)
        self.assertAlmostEqual(ref["third_place_rate"],120/1052)
        self.assertEqual(r["outsider_third_candidate_policy"],
                         "p3 ranking only; rank-band cohort rates descriptive, no bonus")
        self.assertAlmostEqual(candidate["v50_p3"],.23)
        self.assertAlmostEqual(candidate["v50_top3_probability"],.46)
    def test_missing_p3_produces_no_pretend_third_candidate(self):
        r=combine(self.model,self.snap,alpha=.2,off_at=self.off)
        self.assertEqual(r["outsider_third_candidates"],[])

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
