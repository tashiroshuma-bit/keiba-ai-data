import unittest
from scripts.query_jra_official_profile_form_asof import (
    make_features,source_sha_verify,DB)
HORSE="jra:2021103488"
class OfficialHistoryProfileGuardTests(unittest.TestCase):
    def test_real_jra_18_profiles_and_193_rows_sha(self):
        self.assertTrue(source_sha_verify())
    def test_official_profile_asof_nov14_uses_past_only(self):
        r=make_features(DB,HORSE,"2026-11-14T08:00:00+09:00",
            "2026-11-14T16:20:00+09:00",target_surface="芝")
        self.assertEqual(r["status"],"PROVEN_PAST_HISTORY")
        self.assertGreater(r["observed_preoff_features"],0)
        self.assertFalse(r["original_2026_11_08_prediction_retroactive"])
        self.assertFalse(r["published_at_originally_verified"])
        self.assertTrue(all(x["race_date"]<"2026-11-08" for x in r["features"]["recent_races"]))
    def test_original_race_cannot_use_nov8_postrace_profile(self):
        r=make_features(DB,HORSE,"2026-11-08T09:00:00+09:00",
            "2026-11-08T16:25:00+09:00")
        self.assertEqual(r["status"],"PROFILE_NOT_YET_OBSERVED_ASOF")
        self.assertIsNone(r["features"])
    def test_unknown_horse_no_name_guess(self):
        r=make_features(DB,"jra:9999999999",
            "2026-11-14T08:00:00+09:00","2026-11-14T15:00:00+09:00")
        self.assertEqual(r["status"],"MISSING_OFFICIAL_PROFILE")
    def test_future_profile_unsafe_without_timezone(self):
        with self.assertRaises(ValueError):
            make_features(DB,HORSE,"2026-11-14T08:00:00",
                "2026-11-14T15:00:00+09:00")
if __name__=="__main__":unittest.main()
