import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from scripts.v51_preoff_identity_join import audit


class IdentityJoinTests(unittest.TestCase):
    def test_joins_only_prior_dates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db = root / "db.sqlite"
            with sqlite3.connect(db) as c:
                c.execute("CREATE TABLE annual_report_races (race_id TEXT, race_date TEXT)")
                c.execute("CREATE TABLE annual_report_runners (race_id TEXT, horse_number INT, horse_id TEXT, jockey_id TEXT)")
                c.executemany("INSERT INTO annual_report_races VALUES (?,?)", [
                    ("old", "2026-11-01"), ("today", "2026-11-15"), ("future", "2026-11-20")])
                c.executemany("INSERT INTO annual_report_runners VALUES (?,?,?,?)", [
                    (rid, 1, "jra:0000000001", "jra:000001") for rid in ("old", "today", "future")])
            card = {"schema": "jra-v51-live-racecard-v1",
                    "captured_at": "2026-11-14T12:00:00+09:00",
                    "races": [{"race": "upcoming", "race_off_at": "2026-11-15T15:40:00+09:00",
                               "horses": [{"number": 1, "horse_id": "jra:0000000001", "jockey_id": "jra:000001"}]}]}
            path = root / "card.json"
            path.write_text(json.dumps(card))
            result = audit(db, path)
            horse = result["races"][0]["horses"][0]
            self.assertEqual(horse["historical_race_ids"], ["old"])
            self.assertEqual(horse["prior_horse_races"], 1)
            self.assertEqual(horse["prior_jockey_races"], 1)


if __name__ == "__main__":
    unittest.main()
