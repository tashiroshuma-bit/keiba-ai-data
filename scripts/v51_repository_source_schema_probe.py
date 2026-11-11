"""Inspect only existing checked-in small JRA official histories for feature keys.

This is NOT the 362 MB canonical Library v12; it measures data/schema
availability and cannot establish a 2025/2026 V51 ranking uplift.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FILES=(
 "operations/data_updates/jra_official_20261108_all_runner_history_v2.sqlite",
 "operations/data_updates/jra_official_20261108_all_runner_history.sqlite",
)

def probe(path):
    f=Path(path)
    conn=sqlite3.connect(f.resolve().as_uri()+"?mode=ro",uri=True)
    try:
        db_check=conn.execute("pragma quick_check").fetchone()[0]
        if db_check!="ok":raise ValueError("checked-in SQLite invalid")
        tables=[r[0] for r in conn.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
        records=[]
        for t in tables:
            if t.replace("_","").isalnum() is False:
                continue
            cols=[r[1] for r in conn.execute("pragma table_info("+t+")")]
            n=conn.execute("select count(*) from "+t).fetchone()[0]
            candidates=[x for x in cols if any(k in x.lower() for k in (
               "corner","position","passing","weight","class","grade",
               "jockey","horse","race","observed","published","source"))]
            filled={}
            for column in candidates:
                # Both identifiers come solely from SQLite's own schema.
                quoted='"'+column.replace('"','""')+'"'
                filled[column]=conn.execute(
                    "select count(*) from "+t+" where "+quoted+
                    " is not null and trim(cast("+quoted+" as text))!=''"
                ).fetchone()[0]
            records.append({"table":t,"rows":n,
                "source_related_columns":candidates,
                "not_null_not_empty_rows":filled})
        return {"file":str(f.relative_to(ROOT)),"db_bytes":f.stat().st_size,
                "schema_tables":records,"quick_check":"ok"}
    finally:conn.close()

if __name__=="__main__":
    print("V51_SMALL_REPO_DB_SOURCE_SCHEMA="+json.dumps({
       "scope":"REPOSITORY_NONCANONICAL_2026_SMALL_DB_ONLY",
       "proves_historical_v12_2025_feature_coverage":False,
       "proves_true_preoff_weight_publication":False,
       "files":[probe(ROOT/path) for path in FILES]
    },ensure_ascii=False))
