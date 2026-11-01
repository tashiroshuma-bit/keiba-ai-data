"""Validate real archived weekend forecast -> v50 complete probabilities."""
import json
import unittest
from pathlib import Path
from scripts.convert_weekend_to_v50 import adapt
from scripts.v50_rider_overlay import forecast_v50

ARCHIVE=Path("reports/weekend_20261031_1101/ALL_FLAT_RIDER_RECALC_20261031T033252.json")

class TestV50ArchivedReal(unittest.TestCase):
    def test_all_published_real_races(self):
        source=json.loads(ARCHIVE.read_text())
        adapted=adapt(source,model="D")
        self.assertGreaterEqual(len(adapted["races"]),20)
        for race in adapted["races"]:
            with self.subTest(race=race["race"]):
                result=forecast_v50(race["horses"],{})
                self.assertEqual(result["rider_coverage"],0)
                self.assertEqual(result["runner_count"],len(race["horses"]))
                self.assertAlmostEqual(sum(x["p1"] for x in result["v50"]["horses"]),1,places=6)
                self.assertAlmostEqual(sum(x["p2"] for x in result["v50"]["horses"]),1,places=6)
                self.assertAlmostEqual(sum(x["p3"] for x in result["v50"]["horses"]),1,places=6)
                for original in race["horses"]:
                    matched=next(x for x in result["v50"]["horses"] if x["number"]==original["number"])
                    self.assertAlmostEqual(original["p1"],matched["p1"],places=10)

if __name__=="__main__":
    unittest.main()
