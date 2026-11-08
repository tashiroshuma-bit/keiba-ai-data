import unittest
from scripts.v50_direct_place_shadow_2025 import stage_marginals
class StageWisePlaceResearchTests(unittest.TestCase):
    def test_proper_probability_marginals(self):
        p=[.40,.30,.20,.10]
        for a,b in [(1,1),(.75,1.25),(1.5,.5)]:
            p2,p3=stage_marginals(p,a,b)
            self.assertAlmostEqual(sum(p2),1)
            self.assertAlmostEqual(sum(p3),1)
            for i in range(len(p)):
                self.assertGreaterEqual(p2[i],0)
                self.assertGreaterEqual(p3[i],0)
                self.assertLessEqual(p[i]+p2[i]+p3[i],1.000000001)
    def test_no_change_win_probability(self):
        p=[.4,.3,.2,.1];saved=p[:]
        stage_marginals(p,.5,1.5)
        self.assertEqual(saved,p)
    def test_degenerate_fails(self):
        with self.assertRaises(ValueError):
            stage_marginals([.5,.5],1,1)
        with self.assertRaises(ValueError):
            stage_marginals([.7,.2,.2],1,1)
if __name__=="__main__":unittest.main()
