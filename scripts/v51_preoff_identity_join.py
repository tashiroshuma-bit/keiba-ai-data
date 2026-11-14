"""Audit preoff horse/jockey joins against the real canonical v12 SQLite.

Use the authoritative annual_report_runners schema and forbid lookahead.
Does not manufacture features or treat historical result publication as preoff.
"""
import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path


def audit(database, racecard):
    doc = json.loads(Path(racecard).read_text(encoding="utf-8"))
    if doc.get("schema") != "jra-v51-live-racecard-v1":
        raise ValueError("VERIFIED_RACECARD_REQUIRED")
    cutoff = dt.datetime.fromisoformat(doc["captured_at"].replace("Z", "+00:00"))
    if cutoff.tzinfo is None:
        raise ValueError("AWARE_CAPTURE_TIMESTAMP_REQUIRED")
    result = {"schema": "jra-v51-preoff-identity-join-audit-v1", "cutoff": cutoff.isoformat(), "races": []}
    with sqlite3.connect(f"file:{Path(database).resolve()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        tables = {x[0] for x in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"annual_report_races", "annual_report_runners"}
        if not required <= tables:
            raise ValueError("CANONICAL_HISTORY_TABLES_MISSING")
        cols = {r[1] for r in conn.execute("PRAGMA table_info(annual_report_runners)")}
        racecols = {r[1] for r in conn.execute("PRAGMA table_info(annual_report_races)")}
        if not {"race_id", "horse_id", "jockey_id", "horse_number"} <= cols:
            raise ValueError("CANONICAL_RUNNER_ID_COLUMNS_MISSING")
        if not {"race_id", "race_date"} <= racecols:
            raise ValueError("CANONICAL_RACE_DATE_COLUMNS_MISSING")
        for race in doc["races"]:
            off = dt.datetime.fromisoformat(race["race_off_at"].replace("Z", "+00:00"))
            if cutoff >= off:
                raise ValueError("NOT_PREOFF")
            race_day = off.astimezone(dt.timezone(dt.timedelta(hours=9))).date().isoformat()
            entries = []
            for horse in race["horses"]:
                hid, jid = horse["horse_id"], horse["jockey_id"]
                if not hid.startswith("jra:") or not jid.startswith("jra:"):
                    raise ValueError("OFFICIAL_IDS_REQUIRED")
                # Strictly earlier calendar days: excludes future race outcomes
                # and all same-day results (conservative preoff behavior).
                rows = conn.execute("""
                    SELECT r.race_id, r.race_date, h.horse_number, h.horse_id, h.jockey_id
                    FROM annual_report_runners h
                    JOIN annual_report_races r ON r.race_id=h.race_id
                    WHERE h.horse_id=? AND r.race_date<?
                    ORDER BY r.race_date, r.race_id
                """, (hid, race_day)).fetchall()
                rider = conn.execute("""
                    SELECT COUNT(DISTINCT r.race_id) FROM annual_report_runners h
                    JOIN annual_report_races r ON r.race_id=h.race_id
                    WHERE h.jockey_id=? AND r.race_date<?
                """, (jid, race_day)).fetchone()[0]
                entries.append({"number": horse["number"], "horse_id": hid, "jockey_id": jid,
                                "prior_horse_races": len(rows), "prior_jockey_races": rider,
                                "historical_race_ids": [x["race_id"] for x in rows],
                                "latest_history_date": rows[-1]["race_date"] if rows else None})
            result["races"].append({"race": race["race"], "horses": entries})
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--database", required=True)
    p.add_argument("--racecard", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    data = audit(a.database, a.racecard)
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"races": len(data["races"]), "output": str(out)}))
