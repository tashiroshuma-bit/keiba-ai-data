"""Regression checks for ability-adjusted rider research."""
import unittest
from rider_ability_adjusted import rider_residuals

def field(date="2026-10-20",published="2026-10-20T16:00:00+09:00"):
    return [dict(race_id="R1",horse_id=f"h{i}",jockey_id=f"j{i}",
                 horse_pre_race_score=score,field_size=3,finish_position=finish,
                 off_timestamp=date+"T15:00:00+09:00",
                 result_available_at=published,surface="turf",distance_m=1600,
                 track="東京") for i,(score,finish) in enumerate(((.9,1),(.5,2),(.1,3)))]

class RiderAdjustedTest(unittest.TestCase):
    def test_asof(self):
        r=rider_residuals(field(),"2026-11-01T00:00:00+09:00",dict(surface="turf",distance_m=1600,track="東京"))
        self.assertEqual(r["complete_fields"],1)
        self.assertEqual(r["riders"]["j0"]["surface"]["starts"],1)
    def test_future_result_rejected(self):
        r=rider_residuals(field(published="2026-11-02T16:00:00+09:00"),
                          "2026-11-01T00:00:00+09:00",{})
        self.assertEqual(r["complete_fields"],0)
    def test_incomplete_field_rejected(self):
        r=rider_residuals(field()[:2],"2026-11-01T00:00:00+09:00",{})
        self.assertEqual(r["complete_fields"],0)

if __name__=="__main__":
    unittest.main()
