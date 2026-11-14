import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from scripts.v51_verify_forecast_json import validate


class V51ForecastJSONVerificationTests(unittest.TestCase):
    def make_doc(self):
        return {
            "schema": "jra-v51-official-forecast-v1",
            "version": "v51",
            "forecast_asof": "2026-11-14T09:00:00+09:00",
            "v50_used": False,
            "no_live_bets": True,
            "races": [{
                "race": "TEST-001",
                "race_off_at": "2026-11-15T15:00:00+09:00",
                "runners": [
                    {"number": 1, "p1": .2, "p2": .3, "p3": .5, "p_top3": 1.0},
                    {"number": 2, "p1": .3, "p2": .5, "p3": .2, "p_top3": 1.0},
                    {"number": 3, "p1": .5, "p2": .2, "p3": .3, "p_top3": 1.0},
                ],
                "combination_audit": {"mass": 1.0, "ordered_total": 6},
            }]
        }

    def check(self, doc):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "forecast.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            return validate(path)

    def test_valid_contract(self):
        self.assertEqual(self.check(self.make_doc())["status"], "VERIFIED")

    def test_non_normalized_winners_rejected(self):
        doc = self.make_doc()
        doc["races"][0]["runners"][0]["p1"] = .7
        self.assertEqual(self.check(doc)["status"], "INVALID")

    def test_postoff_forecast_rejected(self):
        doc = self.make_doc()
        doc["forecast_asof"] = "2026-11-16T09:00:00+09:00"
        self.assertIn("TEST-001:NOT_PREOFF", self.check(doc)["issues"])

    def test_joint_mass_rejected(self):
        doc = self.make_doc()
        doc["races"][0]["combination_audit"]["mass"] = .5
        self.assertIn("TEST-001:JOINT_MASS_INVALID", self.check(doc)["issues"])


if __name__ == "__main__":
    unittest.main()
