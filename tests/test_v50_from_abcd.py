"""Contract checks for saved A-D -> v50 probability bridge (real v50 overlay)."""
import copy
import unittest
from scripts.v50_from_abcd import bridge


def fixture():
    source = {"created_at": "2026-11-08T08:30:00+09:00", "races": [{
        "race": "京都1R", "date": "2026-11-08", "track": "京都",
        "race_number": 1, "surface": "turf",
        "off_at": "2026-11-08T10:00:00+09:00",
        "runners": [
            {"number": 1, "name": "Alpha", "jockey_id": "jra:1"},
            {"number": 2, "name": "Beta", "jockey_id": "jra:2"},
            {"number": 3, "name": "Gamma", "jockey_id": None}],
        "models": {
            "A": {"horses": [
                {"number": 1, "name": "Alpha", "p1": .5},
                {"number": 2, "name": "Beta", "p1": .3},
                {"number": 3, "name": "Gamma", "p1": .2}]},
            "B": {}, "C": {}, "D": {}}}]}
    rider = {"source": "preoff_horse_ability_adjusted",
             "asof": "2026-11-07T00:00:00+09:00",
             "residuals": {"turf:jra:1": .1, "turf:jra:2": -.1}}
    return source, rider


class TestBridge(unittest.TestCase):
    def test_probability_output_and_all_four_model_labels(self):
        source, rider = fixture()
        before = copy.deepcopy(source)
        result = bridge(source, rider)
        self.assertEqual(source, before)
        self.assertFalse(result["standard_forecast"])
        self.assertEqual(result["races_count"], 1)
        race = result["races"][0]
        self.assertEqual(race["models_available"], ["A", "B", "C", "D"])
        self.assertEqual(len(race["v50"]["horses"]), 3)
        self.assertAlmostEqual(sum(h["p1"] for h in race["v50"]["horses"]), 1.0)
        self.assertEqual(len(result["top5_by_date"]["2026-11-08"]), 1)
        self.assertIn("quinella", race["v50"]["priority"])
        self.assertIn("trio", race["v50"]["priority"])

    def test_refuse_postoff_without_explicit_research(self):
        source, rider = fixture()
        source["created_at"] = "2026-11-08T10:01:00+09:00"
        with self.assertRaisesRegex(ValueError, "after race start"):
            bridge(source, rider)
        self.assertEqual(bridge(source, rider, allow_historical=True)["races_count"], 1)

    def test_refuse_future_rider_snapshot(self):
        source, rider = fixture()
        rider["asof"] = "2026-11-09T00:00:00+09:00"
        with self.assertRaisesRegex(ValueError, "future"):
            bridge(source, rider)

    def test_refuse_misaligned_names(self):
        source, rider = fixture()
        source["races"][0]["runners"][0]["name"] = "Wrong"
        with self.assertRaisesRegex(ValueError, "name mismatch"):
            bridge(source, rider)

    def test_refuse_non_normalized_baseline(self):
        source, rider = fixture()
        source["races"][0]["models"]["A"]["horses"][0]["p1"] = .9
        with self.assertRaises(ValueError):
            bridge(source, rider)

    def test_exclude_jump(self):
        source, rider = fixture()
        source["races"][0]["surface"] = "jump"
        result = bridge(source, rider)
        self.assertEqual(result["races_count"], 0)
        self.assertEqual(result["skipped"][0]["reason"], "unsupported_jump_race")


if __name__ == "__main__":
    unittest.main()
