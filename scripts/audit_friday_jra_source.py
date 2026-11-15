#!/usr/bin/env python3
"""Read-only integrity inspection of the canonical JRA SQLite source.

Usage:
  python scripts/audit_friday_jra_source.py /path/to/jra_2023_2025_v12_horse_ids_full_20261111.sqlite --output audit.json
Never alters the canonical DB and never infers its schema.
"""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sqlite3
import sys

EXPECTED_SHA = "5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd"
EXPECTED_BYTES = 362139648

def audit(path):
    result = {
        "source_path": str(path),
        "observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "expected_sha256": EXPECTED_SHA,
        "expected_size_bytes": EXPECTED_BYTES,
        "status": "NOT_READY",
    }
    if not path.is_file():
        result["reason"] = "source_file_missing"
        return result
    result["actual_size_bytes"] = path.stat().st_size
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    result["actual_sha256"] = h.hexdigest()
    if result["actual_size_bytes"] != EXPECTED_BYTES or result["actual_sha256"] != EXPECTED_SHA:
        result["reason"] = "canonical_source_checksum_or_size_mismatch"
        return result
    try:
        uri = path.resolve().as_uri() + "?mode=ro&immutable=1"
        with sqlite3.connect(uri, uri=True) as con:
            quick = con.execute("PRAGMA quick_check").fetchall()
            result["sqlite_quick_check"] = [x[0] for x in quick]
            if quick != [("ok",)]:
                result["reason"] = "sqlite_integrity_check_failed"
                return result
            tables = con.execute(
                "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"
            ).fetchall()
            result["schema"] = {}
            for name, kind in tables:
                quoted = '"' + name.replace('"', '""') + '"'
                columns = con.execute("PRAGMA table_info(" + quoted + ")").fetchall()
                result["schema"][name] = {
                    "kind": kind,
                    "columns": [{"name": c[1], "type": c[2], "primary_key": bool(c[5])} for c in columns],
                }
        result["status"] = "SOURCE_VERIFIED"
        result["reason"] = "checksum_size_sqlite_integrity_passed; roster_and_results_not_yet_reconciled"
    except (sqlite3.Error, OSError) as e:
        result["reason"] = "sqlite_open_or_schema_error"
        result["error"] = str(e)
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    result = audit(args.database)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0 if result["status"] == "SOURCE_VERIFIED" else 2

if __name__ == "__main__":
    sys.exit(main())
