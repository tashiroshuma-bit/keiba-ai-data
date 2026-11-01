"""Candidate pipeline smoke checks."""
import unittest
from horse_confidence_pipeline import rank_horses,candidate_probabilities,horse_adjustment

class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.h=[dict(number=1,p1=.45),dict(number=2,p1=.55)]
        self.r=[dict(number=1,starts=10,wins=5,seconds=1,thirds=1),
                dict(number=2,starts=1,wins=0,seconds=0,thirds=0)]
    def test_default_unchanged(self):
        self.assertEqual(rank_horses(self.h,self.r)[0]["number"],2)
        self.assertEqual(candidate_probabilities(self.h,self.r),{1:.45,2:.55})
    def test_candidate_normalized(self):
        probs=candidate_probabilities(self.h,self.r,promoted=True)
        self.assertAlmostEqual(sum(probs.values()),1)
        self.assertGreater(probs[1],.45)
    def test_invalid_career(self):
        with self.assertRaises(ValueError):
            horse_adjustment(dict(starts=1,wins=2,seconds=0,thirds=0))

if __name__=="__main__":
    unittest.main()
