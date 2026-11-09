import json
import tempfile
import unittest
from pathlib import Path
from scripts.v51_body_weight_shadow import apply

class V51BodyWeightShadowTests(unittest.TestCase):
    def setUp(self):
        self.asof="2026-11-08T09:00:00+09:00"
        self.v50=[{"number":1,"v50_p1":0.6},{"number":2,"v50_p1":0.4}]
        self.weights=[{"number":1,"asof":self.asof,"weight_observed_at":self.asof,"weight_change_bucket":"-19..-10"},
                      {"number":2,"asof":self.asof,"weight_observed_at":self.asof,"weight_change_bucket":"-3..+3"}]

    def test_normalized_and_original_immutable(self):
        original=json.dumps(self.v50)
        result=apply(self.v50,self.weights,asof=self.asof)
        self.assertEqual(original,json.dumps(self.v50))
        self.assertAlmostEqual(sum(x["v51_shadow_p1"] for x in result["horses"]),1)
        self.assertTrue(result["v50_unchanged"])

    def test_no_future_weights(self):
        self.weights[0]["weight_observed_at"]="2026-11-08T09:01:00+09:00"
        with self.assertRaises(ValueError):apply(self.v50,self.weights,asof=self.asof)

    def test_missing_bucket_rejected(self):
        del self.weights[0]["weight_change_bucket"]
        with self.assertRaises(ValueError):apply(self.v50,self.weights,asof=self.asof)

    def test_incomplete_field_rejected(self):
        with self.assertRaises(ValueError):apply(self.v50,self.weights[:1],asof=self.asof)

if __name__=="__main__":unittest.main()
