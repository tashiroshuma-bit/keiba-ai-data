"""Tests for actor segmentation without using future results."""
import unittest
from actor_segmentation import segment_actor


def row(race, horse, jockey, surface, distance, track, rank, date):
    return dict(race_id=race, horse_id=horse, jockey_id=jockey, surface=surface,
                distance_m=distance, track=track, finish_position=rank,
                off_timestamp=date+"T12:00:00+09:00",
                result_available_at=date+"T19:00:00+09:00")


class ActorSegmentationTest(unittest.TestCase):
    def test_separates_surface_distance_track_and_actor(self):
        rows = [
            row("a", "h1", "j1", "turf", 1200, "東京", 1, "2024-01-01"),
            row("b", "h1", "j2", "dirt", 2000, "京都", 7, "2024-01-02"),
            row("c", "h2", "j1", "turf", 1200, "京都", 2, "2024-01-03"),
            row("d", "h1", "j1", "turf", 1200, "東京", 1, "2025-01-01"),
        ]
        context = dict(surface="turf", distance_m=1200, track="東京")
        horse = segment_actor(rows, "2024-12-31T12:00:00+09:00", "h1", "horse", context)
        jockey = segment_actor(rows, "2024-12-31T12:00:00+09:00", "j1", "jockey", context)
        self.assertEqual(horse["overall"]["starts"], 2)
        self.assertEqual(horse["same_surface"]["starts"], 1)
        self.assertEqual(horse["same_distance_band"]["starts"], 1)
        self.assertEqual(horse["same_track_surface"]["wins"], 1)
        self.assertEqual(jockey["overall"]["starts"], 2)
        self.assertEqual(jockey["same_track_surface"]["starts"], 1)

    def test_missing_identity_not_merged(self):
        history = [row("a", "h1", "j1", "turf", 1600, "東京", 1, "2024-01-01")]
        result = segment_actor(history, "2025-01-01T12:00:00+09:00", None, "horse",
                               dict(surface="turf", distance_m=1600, track="東京"))
        self.assertTrue(result["no_history"])
        self.assertIsNone(result["overall"]["win_rate"])

    def test_future_observation_excluded(self):
        history = [row("a", "h1", "j1", "turf", 1600, "東京", 1, "2024-01-01")]
        result = segment_actor(history, "2024-01-01T15:00:00+09:00", "h1", "horse",
                               dict(surface="turf", distance_m=1600, track="東京"))
        self.assertEqual(result["overall"]["starts"], 0)


if __name__ == "__main__":
    unittest.main()
