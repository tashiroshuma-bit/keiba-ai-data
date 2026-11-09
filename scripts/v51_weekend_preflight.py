"""Fail-closed JRA weekend preflight: distinguish readiness from smoke tests.

No fake production success: a missing canonical SQLite/real source A / original
weight bytes marks NOT_READY, with actionable blockers. Can run unattended in
GitHub Actions or from an automation that materializes the canonical database.
"""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

NEEDED=("scripts/standard_v50_forecast.py",
        "scripts/capture_v50_bodyweight.py",
        "scripts/evaluate_v50_v51_weight_pairs.py",
        "scripts/v51_body_weight_shadow.py")

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda:f.read(1024*1024),b""):h.update(part)
    return h.hexdigest()

def preflight(root,*,database=None,source_a=None,weight_manifest=None,weight_archive=None,phase="final"):
    if phase not in ("morning","final"):
        raise ValueError("preflight phase must be morning or final")
    root=Path(root)
    state=json.loads((root/"PROJECT_STATE.json").read_text())
    checklist={}
    checklist["standard_v50_unchanged"]=state["standard_forecast"]["version"]=="v50"
    checklist["expected_scripts_present"]=all((root/name).is_file() for name in NEEDED)
    checklist["canonical_db_present"]=bool(database and Path(database).is_file())
    if checklist["canonical_db_present"]:
        db=Path(database)
        checklist["canonical_db_size_match"]=db.stat().st_size==state["database"]["bytes"]
        checklist["canonical_db_sha_match"]=sha(db)==state["database"]["sha256"]
        checklist["canonical_db_integrity_ok"]=False
        if checklist["canonical_db_sha_match"]:
            try:
                con=sqlite3.connect(db.resolve().as_uri()+"?mode=ro",uri=True)
                try:
                    checklist["canonical_db_integrity_ok"]=con.execute("PRAGMA quick_check").fetchone()[0]=="ok"
                finally:con.close()
            except sqlite3.DatabaseError:
                checklist["canonical_db_integrity_ok"]=False
    else:
        checklist["canonical_db_size_match"]=False
        checklist["canonical_db_sha_match"]=False
        checklist["canonical_db_integrity_ok"]=False
    checklist["real_source_A_present"]=bool(source_a and Path(source_a).is_file())
    checklist["weight_manifest_present"]=bool(weight_manifest and Path(weight_manifest).is_file())
    checklist["weight_source_bytes_dir_present"]=bool(weight_archive and Path(weight_archive).is_dir())
    required=[key for key in checklist if phase=="final" or key not in (
        "weight_manifest_present","weight_source_bytes_dir_present")]
    blockers=[key for key in required if not checklist[key]]
    return {"status":"READY_TO_ATTEMPT_REAL_PREOFF" if not blockers else "NOT_READY",
            "phase":phase,"weights_not_required_in_morning":phase=="morning",
            "checks":checklist,"blockers":blockers,
            "database_sha256_expected":state["database"]["sha256"],
            "production_model":state["standard_forecast"]["version"],
            "warnings":["Readiness does not verify external source freshness, race-level off times, or successful prediction.",
                        "Source bytes and official publication must be validated at each race's capture.",
                        "No synthetic inputs may count as prospective validation."]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo",default=".")
    p.add_argument("--database")
    p.add_argument("--source-a")
    p.add_argument("--weight-manifest")
    p.add_argument("--weight-archive")
    p.add_argument("--output")
    p.add_argument("--strict",action="store_true")
    p.add_argument("--phase",choices=("morning","final"),default="final")
    a=p.parse_args()
    result=preflight(a.repo,database=a.database,source_a=a.source_a,
                     weight_manifest=a.weight_manifest,weight_archive=a.weight_archive,phase=a.phase)
    output=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if a.output:
        path=Path(a.output)
        if path.exists():raise FileExistsError("preflight report cannot overwrite")
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(output)
    print(output)
    if a.strict and result["status"]!="READY_TO_ATTEMPT_REAL_PREOFF":
        raise SystemExit(2)

if __name__=="__main__": main()
