import unittest
from scripts.v50_rider_overlay import apply_v50, evaluate_p1

class TestV50(unittest.TestCase):
    def test_normalization_and_immutable(self):
        horses=[{"number":1,"jockey_id":"a","p1":.6},{"number":2,"jockey_id":"b","p1":.4}]
        out=apply_v50(horses,{"a":-.5,"b":.5})
        self.assertAlmostEqual(sum(h["v50_p1"] for h in out),1)
        self.assertEqual(horses[0]["p1"],.6)
        self.assertNotIn("v50_p1",horses[0])
        self.assertGreater(out[1]["v50_p1"],.4)
    def test_neutral_matches_v49(self):
        horses=[{"number":1,"p1":.6},{"number":2,"p1":.4}]
        out=apply_v50(horses,{})
        self.assertAlmostEqual(out[0]["v50_p1"],.6)
    def test_paired_metrics(self):
        races=[{"horses":[{"number":1,"jockey_id":"a","p1":.6},{"number":2,"jockey_id":"b","p1":.4}],"actual_winner_number":2}]
        result=evaluate_p1(races,{"a":-1,"b":1})
        self.assertEqual(result["v49_wins"],0)
        self.assertEqual(result["v50_wins"],1)
        self.assertLess(result["v50_logloss"],result["v49_logloss"])
    def test_bad_probabilities_fail_closed(self):
        with self.assertRaises(ValueError):
            apply_v50([{"number":1,"p1":.3},{"number":2,"p1":.4}],{})
if __name__=="__main__":
    unittest.main()
