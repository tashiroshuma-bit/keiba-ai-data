"""Inspect canonical SQLite data contracts before implementing preoff feature joins.

Read-only: never changes source data. Outputs table/column inventories and
relevant row counts to make missing live-feature joins explicit and testable.
"""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

EXPECTED = "5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd"
INTERESTING = ("race", "runner", "horse", "jockey", "identity", "evidence", "result")


def inspect(path, expected=EXPECTED):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError("CANONICAL_DATABASE_MISSING")
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual != expected:
        raise ValueError("CANONICAL_SHA_MISMATCH")
    result = {"schema": "jra-v51-canonical-data-contract-audit-v1", "database_sha256": actual, "tables": []}
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as con:
        if con.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("CANONICAL_SQLITE_INTEGRITY_FAILED")
        tables = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for name in tables:
            if not any(s in name.lower() for s in INTERESTING):
                continue
            quoted = '"' + name.replace('"', '""') + '"'
            columns = [{"name": r[1], "type": r[2], "notnull": bool(r[3]), "primary_key": bool(r[5])} for r in con.execute(f"PRAGMA table_info({quoted})")]
            result["tables"].append({"name": name, "columns": columns, "rows": con.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]})
    result["table_count"] = len(result["tables"])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inspect(args.database), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CANONICAL_SCHEMA_AUDIT", output)
