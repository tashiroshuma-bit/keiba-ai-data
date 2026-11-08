import unittest
from scripts.v51_preoff_provenance_guard import (strict_time,check_historical_observation,
                                                 match_horse_identity)
class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.source={"source_url":"https://www.jra.go.jp/datafile/old.pdf",
          "source_sha256":"a"*64,"off_at":"2025-05-01T14:00:00+09:00",
          "published_at":"2025-05-01T18:00:00+09:00",
          "observed_at":"2025-05-02T10:00:00+09:00"}
    def test_true_historical_publication_before_forecast(self):
        z=check_historical_observation(self.source,
          race_off_at="2025-05-04T11:00:00+09:00",
          forecast_asof="2025-05-04T09:00:00+09:00")
        self.assertTrue(z["validated_asof"])
    def test_assumed_lag_is_not_proof(self):
        self.source["availability_basis"]="assumed_calendar_day_lag_for_research_only"
        with self.assertRaises(ValueError):
            check_historical_observation(self.source,race_off_at="2025-05-04T11:00:00+09:00",
              forecast_asof="2025-05-04T09:00:00+09:00")
    def test_post_forecast_publication_forbidden(self):
        self.source["published_at"]="2025-05-04T10:00:00+09:00"
        self.source["observed_at"]="2025-05-04T10:01:00+09:00"
        with self.assertRaises(ValueError):
            check_historical_observation(self.source,
              race_off_at="2025-05-04T11:00:00+09:00",
              forecast_asof="2025-05-04T09:00:00+09:00")
    def test_unknown_id_not_recovered_from_name(self):
        row={"race_id":"r1","horse_number":7,"horse_name":"馬A"}
        official={"race_id":"r2","horse_number":7,"horse_name":"馬A",
          "horse_id":"jra:2020123456","source_sha256":"b"*64,
          "source_url":"https://www.jra.go.jp/JRADB/accessS.html",
          "observed_at":"2026-11-08T00:00:00+09:00"}
        with self.assertRaises(ValueError):
            match_horse_identity(row,official)
        official["race_id"]="r1"
        self.assertEqual(match_horse_identity(row,official),"jra:2020123456")
if __name__=="__main__":
    unittest.main()
