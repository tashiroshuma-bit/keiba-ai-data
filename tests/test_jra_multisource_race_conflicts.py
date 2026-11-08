import unittest
from scripts.audit_jra_multisource_race_card_conflicts import audit
class MultiSourceMismatchTest(unittest.TestCase):
    def test_unverified_headcount_conflict_not_used(self):
        official={"official":[{"race":"東京1R","status":"official_verified",
            "headcount":11,"url":"https://www.jra.go.jp/official"}]}
        other={"observations":[{"race":"東京1R","source_id":"netkeiba",
            "advertised_field_size":10,"source_url":"https://race.netkeiba.com",
            "snapshot_phase":"unverified_postrace_site_observation",
            "official_results_comparability":True}]}
        d=audit(official,other)
        self.assertEqual(d["conflicts"],1)
        self.assertEqual(d["results"][0]["state"],"QUARANTINE_FIELD_CONFLICT")
        self.assertFalse(d["results"][0]["preoff_feature_eligible"])
    def test_equal_headcount_is_not_preoff_proof(self):
        official={"official":[{"race":"東京1R","status":"official_verified",
            "headcount":11,"url":"https://www.jra.go.jp/official"}]}
        other={"observations":[{"race":"東京1R","source_id":"netkeiba",
            "advertised_field_size":11,"source_url":"https://race.netkeiba.com",
            "snapshot_phase":"unverified_postrace_site_observation",
            "official_results_comparability":True}]}
        d=audit(official,other)
        self.assertEqual(d["conflicts"],0)
        self.assertFalse(d["results"][0]["preoff_feature_eligible"])
if __name__=="__main__":unittest.main()
