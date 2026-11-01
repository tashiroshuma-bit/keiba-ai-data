"""Run immutable real-archive audit and assert exact archived model baselines."""
import unittest
from scripts.audit_v50_real_results import evaluate

class TestV50RealResults(unittest.TestCase):
    def test_20261031_23_real_races(self):
        r=evaluate()
        self.assertFalse(r["official_verified"])
        expected={"A":(10,2.0811748774947647),
                  "B":(8,2.0345358750044205),
                  "C":(8,2.006520722956849),
                  "D":(7,1.9947054451286632)}
        for model,(wins,loss) in expected.items():
            with self.subTest(model=model):
                got=r["model_results"][model]
                self.assertEqual(got["races"],23)
                self.assertEqual(got["v49_wins"],wins)
                self.assertEqual(got["v50_wins"],wins)
                self.assertAlmostEqual(got["v49_logloss"],loss,places=8)
                self.assertAlmostEqual(got["v50_logloss"],loss,places=8)

if __name__=="__main__":
    unittest.main()
