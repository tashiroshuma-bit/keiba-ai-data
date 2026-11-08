import unittest
from scripts.v50_difficulty_flags import assess

class DifficultyShadowTests(unittest.TestCase):
    def test_uniform_large_field_flags_and_does_not_change_model(self):
        model={"horses":[{"number":i+1,"p1":1/16} for i in range(16)]}
        before=[dict(h) for h in model["horses"]]
        r=assess(model)
        self.assertEqual(r["difficulty_level"],"HIGH_REVIEW")
        self.assertTrue(r["caution_flags"])
        self.assertFalse(r["ranking_modified"])
        self.assertFalse(r["rare_upset_predicted"])
        self.assertEqual(model["horses"],before)
    def test_concentrated_field_no_overconfidence_prediction_claim(self):
        x=[.6,.2,.1,.1]
        r=assess({"horses":[{"number":i+1,"p1":p} for i,p in enumerate(x)]})
        self.assertEqual(r["difficulty_level"],"NO_MARKERS")
        self.assertEqual(r["status"],"RESEARCH_CAUTION_NOT_CALIBRATED")
    def test_invalid_probability_fails(self):
        with self.assertRaises(ValueError):
            assess({"horses":[{"number":1,"p1":.4},{"number":2,"p1":.3},
                              {"number":3,"p1":.4}]})

if __name__=="__main__":unittest.main()
