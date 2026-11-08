"""Build real distributable JRA multisource companion SQLite using verified
existing JRA outcome summaries and public provenance catalog.

No original 322MB DB download needed; candidate can be ATTACHED to v11
after v11 passes a complete readback checksum and integrity check.
"""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,sqlite3
from pathlib import Path

try:from scripts.enrich_v11_multisource import SCHEMA,PROVIDERS
except ModuleNotFoundError:from enrich_v11_multisource import SCHEMA,PROVIDERS
ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/"operations/data_updates/multisource_overlay_20261108.sqlite"
AUDIT=ROOT/"operations/data_updates/multisource_overlay_20261108_audit.json"

META="""
CREATE TABLE jra_official_race_checkpoint(
 race_id_text TEXT PRIMARY KEY,
 race_date TEXT NOT NULL,
 track TEXT NOT NULL,
 race_number INTEGER NOT NULL,
 result_headcount INTEGER NOT NULL,
 podium_numbers_json TEXT NOT NULL,
 podium_popularity_json TEXT NOT NULL,
 result_url TEXT NOT NULL,
 result_source_sha256 TEXT NOT NULL,
 result_only_not_preoff INTEGER NOT NULL CHECK(result_only_not_preoff=1));
CREATE TABLE external_race_quarantine(
 id INTEGER PRIMARY KEY,
 race_id_text TEXT NOT NULL,
 provider_id TEXT NOT NULL,
 external_headcount INTEGER NOT NULL,
 jra_result_headcount INTEGER NOT NULL,
 quarantine_reason TEXT NOT NULL,
 external_url TEXT NOT NULL,
 external_snapshot_published_at TEXT,
 preoff_use_allowed INTEGER NOT NULL CHECK(preoff_use_allowed=0));
CREATE TABLE overlay_manifest(
 key TEXT PRIMARY KEY,value TEXT NOT NULL);
"""

def build(output=DEFAULT,audit=AUDIT):
    output=Path(output);audit=Path(audit)
    if output.exists():raise FileExistsError("no overwrite: existing overlay artifact")
    source=json.loads((ROOT/"operations/results/2026-11-08/v50_abcd_settlement.json").read_text())
    rawreg=json.loads((ROOT/"operations/data_updates/five_source_access_and_rights_registry_20261108.json").read_text())
    conflict=json.loads((ROOT/"reports/v51/multisource_race_conflict_audit_20261108.json").read_text())
    v11=json.loads((ROOT/"operations/data_updates/canonical_db_v11_update_verified.json").read_text())
    if len(source["official"])!=36 or len(rawreg["sources"])!=5 or len(conflict["results"])!=1:
        raise ValueError("source dossier not fully reconciled")
    output.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(output)
    try:
        c.execute("PRAGMA foreign_keys=ON")
        c.executescript(SCHEMA)
        c.executescript(META)
        ts=dt.datetime.now(dt.timezone.utc).isoformat()
        for p in rawreg["sources"]:
            cfg=PROVIDERS[p["id"]]
            c.execute("INSERT INTO multi_source_registry VALUES(?,?,?,?,?,?)",
                (p["id"],cfg["host"],cfg["cost"],
                 "permissioned_user_export_only_no_site_crawler",cfg["status"],ts))
        races={}
        for r in source["official"]:
            if r["status"]!="official_verified":raise ValueError("unverified race")
            key=r["race"]
            if key in races:raise ValueError("duplicate official race")
            races[key]=r
            if len(r["top3_numbers"])!=3 or len(r["top3_popularity"])!=3:
                raise ValueError("official podium invalid")
            c.execute("INSERT INTO jra_official_race_checkpoint VALUES(?,?,?,?,?,?,?,?,?,1)",
                (key,"2026-11-08",r["track"],r["race_number"],r["headcount"],
                 json.dumps(r["top3_numbers"]),json.dumps(r["top3_popularity"]),
                 r["url"],r["sha256"]))
        for x in conflict["results"]:
            if x["state"]!="QUARANTINE_FIELD_CONFLICT":continue
            if races[x["race"]]["headcount"]!=x["official_jra_field_size"]:
                raise ValueError("discrepancy refers to mismatched official source")
            c.execute("INSERT INTO external_race_quarantine VALUES(NULL,?,?,?,?,?,?,?,0)",
                (x["race"],x["source"],x["external_field_size"],
                 x["official_jra_field_size"],x["state"],x["external_source"],None))
        manifest={
          "schema":"jra-multisource-companion-v1",
          "base_canonical_database_version":str(v11["version"]),
          "base_canonical_database_sha256":v11["sha256"],
          "historical_and_production_data_unmodified":"true",
          "requires_verified_base_sqlite_readback":"true",
          "new_external_licensed_observation_rows":"0",
          "no_third_party_bulk_scraping":"true",
          "JRA_events":"36","JRA_podium_only":"true"}
        for k,v in manifest.items():
            c.execute("INSERT INTO overlay_manifest VALUES(?,?)",(k,str(v)))
        c.commit()
        if c.execute("PRAGMA quick_check").fetchone()[0]!="ok":
            raise RuntimeError("overlay sqlite quick_check failed")
        if c.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("overlay foreign key check failed")
        counts={
          "sources":c.execute("SELECT count(*) FROM multi_source_registry").fetchone()[0],
          "official_races":c.execute("SELECT count(*) FROM jra_official_race_checkpoint").fetchone()[0],
          "quarantined_external":c.execute("SELECT count(*) FROM external_race_quarantine").fetchone()[0],
          "external_feature_rows":c.execute("SELECT count(*) FROM multi_source_observation").fetchone()[0]}
        if counts!={"sources":5,"official_races":36,
                   "quarantined_external":1,"external_feature_rows":0}:
            raise RuntimeError("overlay population differs from authorized source evidence")
    except Exception:
        c.close();output.unlink(missing_ok=True);raise
    finally:
        try:c.close()
        except Exception:pass
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    report={"schema":"jra-multisource-companion-validation-v1",
        "source_base":"Library canonical v11; not modified here",
        "overlay_sha256":digest,"overlay_size_bytes":output.stat().st_size,
        "overlay_integrity":"ok","counts":counts,
        "base_library_materialization": "REQUIRES_COMPLETE_VERIFIED_READBACK",
        "production_v50_changed":False,
        "third_party_horse_features_imported":0,
        "has_actual_source_registry":True,
        "has_actual_2026_11_08_official_results_index":True,
        "has_actual_public_headcount_discrepancy":True}
    audit.parent.mkdir(parents=True,exist_ok=True)
    audit.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(report,ensure_ascii=False))
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",default=str(DEFAULT))
    p.add_argument("--audit",default=str(AUDIT))
    a=p.parse_args()
    build(a.output,a.audit)
if __name__=="__main__":main()
