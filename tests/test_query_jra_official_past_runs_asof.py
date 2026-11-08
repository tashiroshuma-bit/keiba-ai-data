import shutil,tempfile,unittest
from pathlib import Path
from scripts.query_jra_official_past_runs_asof import DB,verify_saved_companion,get_history

HORSE="jra:2021103488"

class JRAOfficialHistoricalAsOfTests(unittest.TestCase):
    def test_actual_official_497_horse_source_sha_and_integrity(self):
        self.assertTrue(verify_saved_companion())
    def test_actual_winner_history_eligible_for_later_race_only(self):
        v=get_history(DB,HORSE,"2026-11-14T08:00:00+09:00",
            "2026-11-14T16:20:00+09:00",target_race="京都12R_next")
        self.assertEqual(len(v["usable_history"]),1)
        r=v["usable_history"][0]
        self.assertEqual(r["race"],"京都12R")
        self.assertEqual(r["finish_position"],1)
        self.assertEqual(r["horse_name"],"ジャンヌローサ")
        self.assertFalse(r["preoff_evidence_for_original_race"])
        self.assertFalse(v["forecast_modified"])
    def test_same_day_or_pre_capture_history_is_not_a_feature(self):
        v=get_history(DB,HORSE,"2026-11-08T11:00:00+09:00",
            "2026-11-08T16:25:00+09:00",target_race="京都12R")
        self.assertEqual(v["usable_history"],[])
    def test_cannot_use_result_before_postrace_observation(self):
        v=get_history(DB,HORSE,"2026-11-09T06:00:00+09:00",
            "2026-11-09T16:25:00+09:00",target_race="next")
        self.assertEqual(v["usable_history"],[])
    def test_wrong_identity_no_name_fallback(self):
        v=get_history(DB,"jra:9999999999","2026-11-14T08:00:00+09:00",
            "2026-11-14T16:20:00+09:00")
        self.assertEqual(v["usable_history"],[])
    def test_missing_timezone_rejected(self):
        with self.assertRaises(ValueError):
            get_history(DB,HORSE,"2026-11-14T08:00:00",
                "2026-11-14T16:20:00+09:00")
    def test_source_tampering_detected(self):
        with tempfile.TemporaryDirectory() as d:
            name=Path(d)/"source.sqlite";shutil.copyfile(DB,name)
            with name.open("ab") as f:f.write(b"x")
            with self.assertRaises(ValueError):
                verify_saved_companion(name)

if __name__=="__main__":unittest.main()
