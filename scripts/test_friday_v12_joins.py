#!/usr/bin/env python3
"""Canonical-v12-only historical joins and aggregation smoke tests (read-only).

Run: python scripts/test_friday_v12_joins.py /path/to/canonical.sqlite
No network, no external race cards, no other databases.
"""
import argparse
import json
import sqlite3
from pathlib import Path
from audit_friday_jra_source import audit

def schema(conn):
    tables = {}
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        q = '"' + name.replace('"', '""') + '"'
        tables[name] = [row[1] for row in conn.execute("PRAGMA table_info(" + q + ")")]
    return tables

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    integrity = audit(args.database)
    out = {"source": "canonical_v12_only", "source_integrity": integrity["status"], "status": "NOT_READY", "tests": {}}
    if integrity["status"] != "SOURCE_VERIFIED":
        out["reason"] = integrity.get("reason")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 2
    with sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as conn:
        tables = schema(conn)
        out["table_columns"] = tables
        # Inspect actual schema instead of silently assuming joins.
        candidates = {}
        for table, columns in tables.items():
            cols = set(columns)
            candidates[table] = {
                "race_keys": sorted(cols & {"race_id", "race_key"}),
                "horse_keys": sorted(cols & {"horse_id", "jra_horse_id"}),
                "jockey_keys": sorted(cols & {"jockey_id", "jockey_code"}),
                "finish_keys": sorted(cols & {"finish_position", "finish", "rank", "arrival"}),
                "surface_keys": sorted(cols & {"surface", "track_type"}),
                "going_keys": sorted(cols & {"going", "track_condition", "ground_condition"}),
            }
        out["tests"]["schema_discovery"] = "PASS"
        out["join_key_candidates"] = candidates
        out["tests"]["verified_horse_jockey_join"] = "NOT_RUN_SCHEMA_MAPPING_REQUIRED"
        out["tests"]["horse_surface_going_aggregates"] = "NOT_RUN_SCHEMA_MAPPING_REQUIRED"
        out["tests"]["jockey_surface_going_aggregates"] = "NOT_RUN_SCHEMA_MAPPING_REQUIRED"
        out["tests"]["horse_jockey_pair_aggregates"] = "NOT_RUN_SCHEMA_MAPPING_REQUIRED"
        out["reason"] = "No unverified column mapping or inferred finish/going codes allowed; map schema and add explicit join tests next."
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
