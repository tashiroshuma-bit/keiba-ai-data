"""Construct a historical as-of race roster from the canonical database.

Historical race identity and results are used ONLY to identify test targets.
No target race result or same-day outcomes are passed into feature history.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
import sqlite3


def build(database, race_id):
    with sqlite3.connect(f"file:{Path(database).resolve()}?mode=ro", uri=True) as c:
        c.row_factory = sqlite3.Row
        race = c.execute("SELECT * FROM annual_report_races WHERE race_id=?", (race_id,)).fetchone()
        if race is None:
            raise ValueError("RACE_NOT_IN_CANONICAL_DB")
        date = race["race_date"]
        if not date:
            raise ValueError("MISSING_RACE_DATE")
        runners = c.execute(
            "SELECT horse_number, horse_id, jockey_id FROM annual_report_runners WHERE race_id=? ORDER BY horse_number",
            (race_id,),
        ).fetchall()
        if len(runners) < 3:
            raise ValueError("INSUFFICIENT_HISTORICAL_ROSTER")
        missing = [int(r["horse_number"]) for r in runners if not r["horse_id"] or not r["jockey_id"]]
        if missing:
            raise ValueError("MISSING_OFFICIAL_IDS:" + ",".join(map(str, missing)))
        if len({r["horse_number"] for r in runners}) != len(runners):
            raise ValueError("DUPLICATE_RUNNER_NUMBER")
        off = str(race["off_timestamp"]) if "off_timestamp" in race.keys() and race["off_timestamp"] else date + "T23:59:00+09:00"
        # Historical replay does not claim that runner identities were
        # actually observed at this as-of timestamp. This is a retrospective
        # replay candidate, never a certified live forecast.
        card = {
            "schema": "jra-v51-historical-replay-roster-v1",
            "race": race_id, "race_date": date, "race_off_at": off,
            "identity_provenance": "RETROSPECTIVE_NOT_VERIFIED_PREOFF",
            "runners": [
                {"number": r["horse_number"], "horse_id": r["horse_id"],
                 "jockey_id": r["jockey_id"]} for r in runners
            ],
        }
        return card


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--database", required=True)
    p.add_argument("--race-id", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    data = build(a.database, a.race_id)
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    Path(a.output).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"race": data["race"], "runners": len(data["runners"])}))
