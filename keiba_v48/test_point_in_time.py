import unittest
from point_in_time import build, audit_coverage
class Tests(unittest.TestCase):
 def setUp(self):
  self.r={"horse_id":"H1","race_id":"R2","horse_number":"1","off_timestamp":"2025-10-19T15:40:00+09:00","odds_timestamp":"2025-10-19T15:30:00+09:00","pre_off_odds":"4.0","distance_m":"2000","surface":"turf"}
  self.h={"horse_id":"H1","race_id":"R1","off_timestamp":"2025-09-01T15:40:00+09:00","result_available_at":"2025-09-01T16:00:00+09:00","finish_position":"1","distance_m":"1800","surface":"turf"}
 def test_prior_used(self):
  self.assertEqual(build([self.h],[self.r])[0]["prior_4_wins"],1)
 def test_future_publication_excluded(self):
  h={**self.h,"result_available_at":"2025-10-19T15:40:00+09:00"}
  self.assertEqual(build([h],[self.r])[0]["prior_4_starts"],0)
 def test_same_race_excluded(self):
  self.assertEqual(build([{**self.h,"race_id":"R2"}],[self.r])[0]["prior_4_starts"],0)
 def test_late_odds_rejected(self):
  with self.assertRaises(ValueError):build([],[{**self.r,"odds_timestamp":"2025-10-19T15:39:00+09:00"}])
 def test_missing_time_zone(self):
  with self.assertRaises(ValueError):build([],[{**self.r,"off_timestamp":"2025-10-19T15:40:00"}])
 def test_coverage_gate(self):
  x=audit_coverage([{**self.r,"field_complete":"yes","source_url":"https://jra.go.jp","finish_position":"1"}])
  self.assertTrue(x[0]["field_complete_attested"])
 def test_duplicate_numbers(self):
  self.assertFalse(audit_coverage([{**self.r,"field_complete":"yes"},{**self.r,"field_complete":"yes"}])[0]["unique_numbers"])
if __name__=="__main__":unittest.main()
