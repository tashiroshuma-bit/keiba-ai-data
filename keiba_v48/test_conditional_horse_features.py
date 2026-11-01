"""Unit checks for conditional horse features; research-only."""
import unittest
from datetime import datetime, timezone
from conditional_horse_features import horse_features, distance_band

CUTOFF="2026-11-01T00:00:00+09:00"

class ConditionalHorseTest(unittest.TestCase):
    def test_distance_bands(self):
        self.assertEqual([distance_band(x) for x in (1200,1600,2000,3000)],
                         ["sprint","mile","middle","long"])
    def test_future_results_excluded(self):
        history=[dict(off_timestamp="2026-10-30T10:00:00+09:00",
                      result_available_at="2026-11-02T10:00:00+09:00",
                      finish_position=1,surface="turf",distance_m=1600,going="good")]
        result=horse_features(history,CUTOFF,dict(surface="turf",distance_m=1600,going="good"))
        self.assertEqual(result["overall"]["starts"],0)
        self.assertEqual(result["overall"]["score"],.15)
    def test_condition_shrinkage(self):
        history=[dict(off_timestamp="2026-10-20T10:00:00+09:00",
                      result_available_at="2026-10-20T15:00:00+09:00",
                      finish_position=2,surface="turf",distance_m=1600,going="good",track="東京")]
        result=horse_features(history,CUTOFF,dict(surface="turf",distance_m=1600,going="heavy",track="東京"))
        self.assertEqual(result["overall"]["starts"],1)
        self.assertEqual(result["going"]["starts"],0)
        self.assertFalse(result["going"]["observed"])
        self.assertEqual(result["distance"]["starts"],1)

if __name__=="__main__":
    unittest.main()
