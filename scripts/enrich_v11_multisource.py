"""Provenance-first multi-source JRA feature extension, no web crawler.

Usage:
  python -m scripts.enrich_v11_multisource --database /path/to/v11.sqlite \
    --records records.jsonl --output /path/to/v12_candidate.sqlite
Only explicit rights-authorized user exports / verified factual observations
may be ingested. Never copy a third party site's complete data by scraping.
Preserve original database; journal validated evidence in append-only tables.
"""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,math,re,shutil,sqlite3
from pathlib import Path
from urllib.parse import urlparse

PROVIDERS={
    "jra_official":{"host":"jra.go.jp","auto":False,"cost":"free_public",
       "status":"manual_verified_facts_only"},
    "netkeiba":{"host":"netkeiba.com","auto":False,"cost":"mixed",
       "status":"rights_authorization_required"},
    "jra_van_next":{"host":"jra-van.jp","auto":False,"cost":"subscription",
       "status":"licensed_export_only"},
    "umarand":{"host":"umarand.com","auto":False,"cost":"mixed",
       "status":"rights_authorization_required"},
    "smartrc":{"host":"smartrc.jp","auto":False,"cost":"mixed",
       "status":"rights_authorization_required"}}
FIELDS={
    "bloodline_sire","bloodline_dam","bloodline_damsire","pedigree_sire_line",
    "pedigree_damsire_line","rider_name","trainer_name","rider_id",
    "past_finish","past_speed_index","past_last3f_seconds",
    "prior_opponent_strength","prior_running_style","prior_corner4",
    "workout_hill_4f_seconds","workout_last1f_seconds",
    "horse_weight_kg","horse_weight_change_kg","assigned_weight_kg",
    "race_track_going","preoff_win_odds","final_win_odds",
    "turf_course_familiarity","distance_history_start_count",
}
FLOAT_FIELDS={"past_speed_index","past_last3f_seconds","prior_opponent_strength",
              "prior_corner4","workout_hill_4f_seconds",
              "workout_last1f_seconds","horse_weight_kg","horse_weight_change_kg",
              "assigned_weight_kg","preoff_win_odds","final_win_odds",
              "turf_course_familiarity","distance_history_start_count"}
RESULT_FIELDS={"past_finish","final_win_odds"}
TIME_FORMAT="ISO8601 timestamp with numeric UTC offset"

SCHEMA="""
CREATE TABLE IF NOT EXISTS multi_source_registry(
 source_id TEXT PRIMARY KEY,site_host TEXT NOT NULL,cost TEXT NOT NULL,
 ingest_mode TEXT NOT NULL,rights_status TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS multi_source_observation(
 observation_id TEXT PRIMARY KEY,source_id TEXT NOT NULL,
 official_race_id TEXT NOT NULL,horse_number INTEGER NOT NULL CHECK(horse_number BETWEEN 1 AND 18),
 source_horse_id TEXT,verified_jra_horse_id TEXT,feature_key TEXT NOT NULL,
 value_text TEXT,value_num REAL,
 observed_at TEXT NOT NULL,published_at TEXT,forecast_asof TEXT,off_at TEXT,
 source_url TEXT NOT NULL,source_sha256 TEXT NOT NULL,
 rights_basis TEXT NOT NULL,rights_reference TEXT,
 phase TEXT NOT NULL CHECK(phase IN ('preoff_proven','postrace','unverified')),
 usable_for_v50_v51_preoff INTEGER NOT NULL DEFAULT 0 CHECK(usable_for_v50_v51_preoff IN (0,1)),
 created_at TEXT NOT NULL,
 FOREIGN KEY(source_id) REFERENCES multi_source_registry(source_id),
 UNIQUE(source_id,official_race_id,horse_number,feature_key,observed_at,source_sha256)
);
CREATE INDEX IF NOT EXISTS multi_source_observation_race
 ON multi_source_observation(official_race_id,horse_number,feature_key);
CREATE INDEX IF NOT EXISTS multi_source_observation_phase
 ON multi_source_observation(usable_for_v50_v51_preoff,forecast_asof);
CREATE TABLE IF NOT EXISTS multi_source_import_audit(
 batch_sha256 TEXT PRIMARY KEY,record_count INTEGER NOT NULL,
 inserted INTEGER NOT NULL,duplicates INTEGER NOT NULL,rejected INTEGER NOT NULL,
 status TEXT NOT NULL,output_sha256 TEXT,created_at TEXT NOT NULL
);
"""

def time(value):
    if value is None:return None
    v=dt.datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if v.tzinfo is None or v.utcoffset() is None:raise ValueError(TIME_FORMAT)
    return v

def source_ok(site,url):
    u=urlparse(url)
    host=u.hostname or ""
    registered=PROVIDERS[site]["host"]
    return u.scheme=="https" and (host==registered or host.endswith("."+registered))

def identify(rec):
    """Crosswalk is never inferred from name and is not changed implicitly."""
    ident=rec.get("verified_jra_horse_id")
    if ident is None:return None
    evidence=rec.get("horse_id_evidence") or {}
    if (not re.fullmatch(r"jra:\d{10}",str(ident)) or
        evidence.get("horse_id")!=ident or
        evidence.get("race_id")!=rec["official_race_id"] or
        evidence.get("horse_number")!=rec["horse_number"] or
        not source_ok("jra_official",str(evidence.get("url",""))) or
        not re.fullmatch("[0-9a-f]{64}",str(evidence.get("sha256",""))) or
        not evidence.get("observed_at")):
        raise ValueError("official horse ID requires exact JRA race/number/link/hash evidence")
    if time(evidence["observed_at"])>time(rec["observed_at"]):
        raise ValueError("official ID proof first observed after source observation")
    return ident

def normalize(rec):
    src=rec["source_id"]
    if src not in PROVIDERS:raise ValueError("unregistered provider")
    if rec["feature_key"] not in FIELDS:raise ValueError("field not whitelisted")
    if not re.fullmatch(r"[a-zA-Z0-9_\-:]{5,128}",str(rec["official_race_id"])):
        raise ValueError("race ID not canonical-safe")
    n=rec["horse_number"]
    if not isinstance(n,int) or isinstance(n,bool) or not 1<=n<=18:
        raise ValueError("horse number 1-18 required")
    if not source_ok(src,str(rec["source_url"])):
        raise ValueError("source URL provider mismatch")
    digest=str(rec["source_sha256"])
    if not re.fullmatch(r"[0-9a-f]{64}",digest):
        raise ValueError("source body sha256 required")
    observed=time(rec["observed_at"])
    published=time(rec.get("published_at"))
    asof=time(rec.get("forecast_asof"))
    off=time(rec.get("off_at"))
    if observed is None:raise ValueError("source observed_at missing")
    if rec["source_id"]!="jra_official":
        if (rec.get("rights_basis") not in ("license","specific_permission","lawful_manual_observation") or
            not rec.get("rights_reference")):
            raise ValueError("third-party import requires recorded rights basis and reference")
        if rec.get("acquisition_mode")=="bulk_scrape":
            raise ValueError("third-party bulk scraping is not enabled")
    elif rec.get("rights_basis") not in ("official_public_factual","specific_permission"):
        raise ValueError("JRA facts must be sourced and independently verified")
    value=rec.get("value")
    if value is None or isinstance(value,(list,dict,bool)):
        raise ValueError("single typed factual value required")
    if rec["feature_key"] in FLOAT_FIELDS:
        if not isinstance(value,(float,int)) or not math.isfinite(value):
            raise ValueError("numeric value required")
        num=float(value);txt=None
        if rec["feature_key"] in ("preoff_win_odds","final_win_odds") and num<1:
            raise ValueError("odds <1 invalid")
    else:
        num=None;txt=str(value)
        if not txt or len(txt)>250:raise ValueError("empty or overlong field")
    official=identify(rec)
    preoff=bool(
        rec["feature_key"] not in RESULT_FIELDS and
        published is not None and asof is not None and off is not None and
        published<=observed<=asof<off)
    if rec["feature_key"]=="preoff_win_odds":
        preoff=preoff and rec.get("odds_kind")=="observed_actual" and rec.get("complete_market_snapshot") is True
    if published and published>observed:
        raise ValueError("published later than source observed")
    if asof and off and asof>=off:
        raise ValueError("forecast not before off")
    # Strict ID evidence mandatory for horse-level pre-off training, not just number.
    preoff=preoff and official is not None
    phase="preoff_proven" if preoff else (
        "postrace" if rec["feature_key"] in RESULT_FIELDS or (off and observed>=off) else "unverified")
    if rec.get("requires_preoff") is True and not preoff:
        raise ValueError("record requested preoff but publication/identity/odds proof incomplete")
    seed={k:rec.get(k) for k in (
        "source_id","official_race_id","horse_number","feature_key",
        "source_sha256","observed_at","value")}
    identity=hashlib.sha256(json.dumps(seed,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return (identity,src,str(rec["official_race_id"]),n,rec.get("source_horse_id"),official,
            rec["feature_key"],txt,num,str(rec["observed_at"]),
            rec.get("published_at"),rec.get("forecast_asof"),rec.get("off_at"),
            rec["source_url"],digest,rec["rights_basis"],rec.get("rights_reference"),
            phase,int(preoff),dt.datetime.now(dt.timezone.utc).isoformat())

def sha256_file(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()

def core_counts(conn):
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    names=("annual_report_races","annual_report_runners","jra_20261108_official_podium_supplement")
    return {n:conn.execute('SELECT count(*) FROM "'+n+'"').fetchone()[0]
            for n in names if n in tables}

def upgrade(database,records,output,expected_source_sha256=None):
    database=Path(database);records=Path(records);output=Path(output)
    if output.exists():raise FileExistsError("never overwrite canonical database without independent verification")
    if database.resolve()==output.resolve():raise ValueError("source and output same")
    if not database.is_file() or not records.is_file():
        raise FileNotFoundError("database and permitted records JSONL required")
    if expected_source_sha256 and sha256_file(database)!=expected_source_sha256:
        raise ValueError("canonical source SHA256 mismatch: stop before migration")
    raw=records.read_bytes();lines=[x for x in raw.splitlines() if x.strip()]
    if not lines:raise ValueError("no real authorized records: no fake DB expansion")
    rows=[normalize(json.loads(x)) for x in lines]
    output.parent.mkdir(parents=True,exist_ok=True)
    conn_in=sqlite3.connect(f"file:{database}?mode=ro",uri=True)
    conn_out=sqlite3.connect(output)
    try:
        original_counts=core_counts(conn_in)
        conn_in.backup(conn_out)
        conn_out.execute("PRAGMA foreign_keys=ON")
        conn_out.executescript(SCHEMA)
        now=dt.datetime.now(dt.timezone.utc).isoformat()
        for key,info in PROVIDERS.items():
            conn_out.execute("""INSERT OR IGNORE INTO multi_source_registry
             (source_id,site_host,cost,ingest_mode,rights_status,created_at)
             VALUES(?,?,?,?,?,?)""",
                (key,info["host"],info["cost"],"explicit_authorized_export_only",info["status"],now))
        # Source registry inserts already opened SQLite's implicit transaction.
        # Keep registry and observations atomic instead of starting a second BEGIN.
        inserted=duplicates=0
        for row in rows:
            cur=conn_out.execute("""INSERT OR IGNORE INTO multi_source_observation
             (observation_id,source_id,official_race_id,horse_number,source_horse_id,
              verified_jra_horse_id,feature_key,value_text,value_num,observed_at,
              published_at,forecast_asof,off_at,source_url,source_sha256,rights_basis,
              rights_reference,phase,usable_for_v50_v51_preoff,created_at)
             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",row)
            inserted+=cur.rowcount
            duplicates+=1-cur.rowcount
        digest=hashlib.sha256(raw).hexdigest()
        conn_out.execute("""INSERT INTO multi_source_import_audit
         (batch_sha256,record_count,inserted,duplicates,rejected,status,created_at)
         VALUES(?,?,?,?,0,'validated',?)""",(digest,len(rows),inserted,duplicates,now))
        conn_out.commit()
        assert conn_out.execute("PRAGMA quick_check").fetchone()[0]=="ok"
        assert not conn_out.execute("PRAGMA foreign_key_check").fetchall()
        if original_counts!=core_counts(conn_out):
            raise ValueError("historical tables altered by multi-source migration")
        result={"source_sha256":sha256_file(database),
         "output_sha256":sha256_file(output),
         "import_batch_sha256":digest,"records":len(rows),"inserted":inserted,
         "duplicates":duplicates,"preoff_usable":conn_out.execute(
          "SELECT count(*) FROM multi_source_observation WHERE usable_for_v50_v51_preoff=1"
          ).fetchone()[0],
         "by_provider":dict(conn_out.execute(
          "SELECT source_id,count(*) FROM multi_source_observation GROUP BY source_id"
          ).fetchall()),
         "original_history_unchanged":True,"core_history_counts":original_counts,
         "integrity":"ok"}
        return result
    except Exception:
        conn_out.rollback();conn_out.close()
        output.unlink(missing_ok=True)
        raise
    finally:
        conn_in.close()
        try:conn_out.close()
        except Exception:pass

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--database",required=True)
    p.add_argument("--records",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--expected-source-sha256",required=True)
    args=p.parse_args()
    print(json.dumps(upgrade(args.database,args.records,args.output,
        expected_source_sha256=args.expected_source_sha256),ensure_ascii=False))
if __name__=="__main__":main()
