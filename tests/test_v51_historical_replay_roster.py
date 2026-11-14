import sqlite3
import tempfile
import unittest
from pathlib import Path
from scripts.v51_historical_replay_roster import build


class HistoricalReplayRosterTests(unittest.TestCase):
    def test_historical_roster_is_not_mislabelled_preoff(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "test.sqlite"
            with sqlite3.connect(db) as c:
                c.execute("CREATE TABLE annual_report_races(race_id TEXT, race_date TEXT, off_timestamp TEXT)")
                c.execute("CREATE TABLE annual_report_runners(race_id TEXT, horse_number INTEGER, horse_id TEXT, jockey_id TEXT)")
                c.execute("INSERT INTO annual_report_races VALUES('race1','2025-10-01','2025-10-01T15:00:00+09:00')")
                c.executemany("INSERT INTO annual_report_runners VALUES(?,?,?,?)",
                              [("race1", n, f"jra:{n:010d}", "jra:000001") for n in (1,2,3)])
            card = build(db, "race1")
            self.assertEqual(card["schema"], "jra-v51-historical-replay-roster-v1")
            self.assertEqual(card["identity_provenance"], "RETROSPECTIVE_NOT_VERIFIED_PREOFF")
            self.assertEqual(len(card["runners"]), 3)

    def test_missing_identity_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "test.sqlite"
            with sqlite3.connect(db) as c:
                c.execute("CREATE TABLE annual_report_races(race_id TEXT, race_date TEXT, off_timestamp TEXT)")
                c.execute("CREATE TABLE annual_report_runners(race_id TEXT, horse_number INTEGER, horse_id TEXT, jockey_id TEXT)")
                c.execute("INSERT INTO annual_report_races VALUES('race1','2025-10-01',NULL)")
                c.executemany("INSERT INTO annual_report_runners VALUES(?,?,?,?)",
                              [("race1", n, None if n == 1 else f"jra:{n:010d}", "jra:000001") for n in (1,2,3)])
            with self.assertRaisesRegex(ValueError, "MISSING_OFFICIAL_IDS"):
                build(db, "race1")


if __name__ == "__main__":
    unittest.main()
