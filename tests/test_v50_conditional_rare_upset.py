import unittest
from scripts.v50_conditional_rare_upset import assessment

class ConditionalRareUpsetResearchTest(unittest.TestCase):
    def setUp(self):
        self.model={"horses":[{"number":i+1,"p1":1/16} for i in range(16)]}
        self.rule={"min_field":14,"max_top1":0.16,"max_gap":0.04,"min_entropy":0.95}
        self.extended={"selected":self.rule}
        self.policy={"enabled":False,"candidate_rule":None,"candidate_holdout":None}
    def test_default_never_changes_distribution(self):
        before=[h["p1"] for h in self.model["horses"]]
        r=assessment(self.model,self.policy,extended=self.extended)
        self.assertTrue(r["extended_2025_criteria_match"])
        self.assertEqual(r["mode"],"STANDARD_V50")
        self.assertTrue(r["research_watch_only"])
        self.assertFalse(r["probability_boost_applied"])
        self.assertEqual([h["p1"] for h in self.model["horses"]],before)
    def test_deny_unverified_enabled_policy(self):
        self.policy.update({"enabled":True,"candidate_rule":self.rule,
            "candidate_holdout":{"extreme_upsets":3,"extreme_hits":2,
              "flag_rate":.1,"lift_vs_base":3.0}})
        r=assessment(self.model,self.policy,extended=self.extended)
        self.assertEqual(r["mode"],"STANDARD_V50")
        self.assertFalse(r["rare_upset_model_activation_allowed"])
    def test_explicit_independent_validated_only(self):
        self.policy.update({"enabled":True,"candidate_rule":self.rule,
          "candidate_holdout":{"extreme_upsets":3,"extreme_hits":2,
             "flag_rate":.1,"lift_vs_base":3.0},
          "model_family_validated":"canonical_v50",
          "reviewed_on_independent_dates":True})
        r=assessment(self.model,self.policy)
        self.assertEqual(r["mode"],"RARE_UPSET_REVIEW")
        self.assertTrue(r["rare_upset_model_activation_allowed"])
        self.assertFalse(r["probability_boost_applied"])
    def test_missing_confidence_rejected(self):
        self.model["horses"][0]["p1"]=.6
        with self.assertRaises(ValueError):
            assessment(self.model,self.policy)
    def test_no_flag_for_clear_favorite_even_validated(self):
        model={"horses":[{"number":i+1,"p1":(.5 if i==0 else .5/15)} for i in range(16)]}
        self.policy.update({"enabled":True,"candidate_rule":self.rule,
          "candidate_holdout":{"extreme_upsets":3,"extreme_hits":2,
             "flag_rate":.1,"lift_vs_base":3.0},
          "model_family_validated":"canonical_v50","reviewed_on_independent_dates":True})
        r=assessment(model,self.policy)
        self.assertEqual(r["mode"],"STANDARD_V50")
        self.assertFalse(r["rare_upset_model_activation_allowed"])

if __name__=="__main__":unittest.main()
