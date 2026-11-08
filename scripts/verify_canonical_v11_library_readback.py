"""Fail-closed canonical SQLite v11 readback integrity verification.

Requires actual Library v11 bytes materialized in the execution runtime.
DO NOT infer a valid hash from Library metadata or file size alone.
The validated postrace 495-runner supplemental SQLite must remain separate.
"""
import argparse,hashlib,json,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXPECTED_SHA="7206c787e6b13616e0ac1a0950d31a2539188c466fd369bdcd916f4f58f59627"
EXPECTED_BYTES=322170880
REPORT=ROOT/"operations/data_updates/canonical_v11_materialized_readback_check.json"
def sha256(path):
    h=hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda:fp.read(8*1024*1024),b""):h.update(chunk)
    return h.hexdigest()
def check(path):
    p=Path(path)
    if not p.exists():raise FileNotFoundError(str(p))
    size=p.stat().st_size
    hash_value=sha256(p)
    result={"source_path":str(p),"size_bytes":size,"sha256":hash_value,
       "expected_size_bytes":EXPECTED_BYTES,"expected_sha256":EXPECTED_SHA,
       "size_match":size==EXPECTED_BYTES,"sha256_match":hash_value==EXPECTED_SHA,
       "integrity_check":None,"foreign_key_errors":None,
       "historical_races":None,"historical_runner_rows":None,
       "postrace_supplement_rows":None,"validated":False}
    if not (result["size_match"] and result["sha256_match"]):
        return result
    db=sqlite3.connect(f"file:{p.resolve()}?mode=ro",uri=True)
    try:
        result["integrity_check"]=db.execute("PRAGMA integrity_check").fetchone()[0]
        result["foreign_key_errors"]=len(db.execute("PRAGMA foreign_key_check").fetchall())
        result["historical_races"]=db.execute("SELECT count(*) FROM annual_report_races").fetchone()[0]
        result["historical_runner_rows"]=db.execute("SELECT count(*) FROM annual_report_runners").fetchone()[0]
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jra_20261108_official_podium_supplement'").fetchone()
        if exists:
            result["postrace_supplement_rows"]=db.execute("SELECT count(*) FROM jra_20261108_official_podium_supplement").fetchone()[0]
        result["validated"]=(result["integrity_check"]=="ok" and
          result["foreign_key_errors"]==0 and result["historical_races"]==13176 and
          result["historical_runner_rows"]==181345 and result["postrace_supplement_rows"]==108)
    finally:db.close()
    return result
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--database",required=True)
    p.add_argument("--output")
    args=p.parse_args()
    res=check(args.database)
    print(json.dumps(res,ensure_ascii=False,indent=2))
    if args.output:
        Path(args.output).write_text(json.dumps(res,ensure_ascii=False,indent=2)+"\n")
    if not res["validated"]:raise SystemExit(1)
if __name__=="__main__":main()
