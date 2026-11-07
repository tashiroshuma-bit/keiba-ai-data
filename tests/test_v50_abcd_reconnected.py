"""Audit full fields and unchanged original A in Nov 7/8 A-D reconnection."""
import json
import math
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RECON=ROOT/"operations/predictions/2026-11-07/v50_weekend_abcd_reconnected.json"
ORIG=ROOT/"operations/predictions/2026-11-07/v50_weekend_research.json"

class TestV50ABCDResearchOutput(unittest.TestCase):
    def test_saved_four_model_probabilities(self):
        original=json.loads(ORIG.read_text())
        updated=json.loads(RECON.read_text())
        self.assertEqual(updated["requested"],72)
        self.assertGreaterEqual(updated["reconnected"],1)
        prior={(r["date"],r["race"]):r for r in original["races"]}
        self.assertEqual(len(updated["races"]),72)
        successes=0
        for r in updated["races"]:
            if r["status"]!="abcd_reconnected":
                continue
            successes+=1
            old=prior[(r["date"],r["race"])]
            p_old={h["number"]:h["p1"] for h in old["v50"]["horses"]}
            p_new={h["number"]:h["p1"] for h in r["models"]["A"]["horses"]}
            self.assertEqual(p_old,p_new)
            expected=set(p_old)
            self.assertEqual(set(int(n) for n in r["external_indices"]),expected)
            for label in "ABCD":
                horses=r["models"][label]["horses"]
                self.assertEqual(len(horses),len(expected))
                self.assertEqual(set(h["number"] for h in horses),expected)
                for column in ("p1","p2","p3"):
                    values=[h[column] for h in horses]
                    self.assertTrue(all(math.isfinite(v) and 0<=v<=1 for v in values))
                    self.assertAlmostEqual(sum(values),1,places=8)
                for key in ("single","quinella","trio"):
                    tickets=r["models"][label]["priority"][key]["tickets"]
                    self.assertTrue(all(0<=t["p"]<=1 for t in tickets))
        self.assertEqual(successes,updated["reconnected"])
    def test_no_unverified_full_field_is_reported_as_reconnected(self):
        data=json.loads(RECON.read_text())
        rejected=[r for r in data["races"] if r["status"]=="external_rejected"]
        self.assertEqual(len(rejected),data["rejected"])
        for r in rejected:
            self.assertNotIn("models",r)

if __name__=="__main__":
    unittest.main()
