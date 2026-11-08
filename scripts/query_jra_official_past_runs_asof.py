"""As-of official horse race history for future JRA v51 research.

The historical result MUST have been observed before the next target race
and at least two calendar days earlier. A current-race finish, current-race
odds, or any post-asof information is never exported. Identity is matched
by exact JRA profile ID only, no name joins.
"""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,sqlite3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/"operations/data_updates/jra_official_20261108_all_runner_history_v2.sqlite"
AUDIT=ROOT/"operations/data_updates/jra_official_20261108_all_runner_history_v2_audit.json"

def parse_timestamp(s):
    d=dt.datetime.fromisoformat(str(s).replace("Z","+00:00"))
    if not d.tzinfo or d.utcoffset() is None:
        raise ValueError("timezone-bearing forecast timestamp is mandatory")
    return d

def get_history(database,official_id,forecast_asof,target_off_at,
                target_race=None,minimum_lag_calendar_days=2):
    if not isinstance(official_id,str) or not official_id.startswith("jra:"):
        raise ValueError("official JRA horse ID required")
    if not (len(official_id)==14 and official_id[4:].isdigit()):
        raise ValueError("official JRA 10-digit horse ID required")
    asof=parse_timestamp(forecast_asof)
    off=parse_timestamp(target_off_at)
    if not asof<off:
        raise ValueError("forecast must precede target race")
    if minimum_lag_calendar_days<2:
        raise ValueError("research safety minimum two-day historical race lag")
    db=Path(database)
    if not db.exists():raise FileNotFoundError(str(db))
    conn=sqlite3.connect(f"file:{db.resolve()}?mode=ro",uri=True)
    conn.row_factory=sqlite3.Row
    try:
        if conn.execute("PRAGMA quick_check").fetchone()[0]!="ok":
            raise ValueError("history overlay invalid")
        source=conn.execute("""SELECT r.*,s.observed_at AS evidence_observed_at,
            s.source_url AS evidence_url,s.source_sha256 AS evidence_sha256
            FROM runner_postrace r JOIN source_race s USING(race)
            WHERE r.horse_id=? ORDER BY s.observed_at DESC""",(official_id,)).fetchall()
        if not source:return {"horse_id":official_id,"usable_history":[],
                              "rejected_history":0,"asof":forecast_asof,
                              "forecast_modified":False}
        accepted=[];rejected=0
        for record in source:
            h=dict(record)
            # Race itself is determined from current evidence, never same-race data.
            if (target_race and h["race"]==target_race):
                rejected+=1;continue
            # Fixed historical data date of this SOURCE DB; future DB updates
            # should add a proper race_date column instead of inferring.
            race_date=dt.date.fromisoformat("2026-11-08")
            if (off.date()-race_date).days<minimum_lag_calendar_days:
                rejected+=1;continue
            observed=parse_timestamp(h["observed_at"])
            if observed>asof or parse_timestamp(h["evidence_observed_at"])>asof:
                rejected+=1;continue
            if h["source_sha256"]!=h["evidence_sha256"]:
                raise ValueError("history row and evidence SHA mismatch")
            if h["result_only_not_prediction_feature"]!=1:
                raise ValueError("historical result must be marked as postrace")
            accepted.append({
                "race":h["race"],"race_date":"2026-11-08",
                "horse_id":h["horse_id"],"horse_name":h["horse_name"],
                "official_profile_url":h["horse_profile_url"],
                "finish_position":h["finish_position"],
                "assigned_weight_kg":h["assigned_weight_kg"],
                "race_time":h["race_time"],
                "corner_positions":h["corner_positions"],
                "last3f_seconds":h["estimated_last3f_seconds"],
                "bodyweight_kg":h["bodyweight_kg"],
                "bodyweight_delta_kg":h["bodyweight_delta_kg"],
                "jockey_name":h["jockey_name"],
                "observed_at":h["observed_at"],
                "source_url":h["source_url"],
                "source_sha256":h["source_sha256"],
                "strict_usage":"historical_past_run_only_after_actual_observation",
                "preoff_evidence_for_original_race":False})
        return {"horse_id":official_id,"usable_history":accepted,
                "rejected_history":rejected,"asof":forecast_asof,
                "forecast_modified":False}
    finally:conn.close()

def verify_saved_companion(path=DB,audit=AUDIT):
    expected=json.loads(Path(audit).read_text())
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(2**20),b""):
            h.update(block)
    if h.hexdigest()!=expected["sqlite_sha256"] or Path(path).stat().st_size!=expected["sqlite_bytes"]:
        raise ValueError("JRA official history supplement source SHA/bytes mismatch")
    if expected["races_verified"]!=36 or expected["official_runner_ids"]!=497:
        raise ValueError("official history supplement coverage incomplete")
    return True

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--horse-id",required=True)
    p.add_argument("--asof",required=True)
    p.add_argument("--off-at",required=True)
    p.add_argument("--race")
    a=p.parse_args()
    verify_saved_companion()
    print(json.dumps(get_history(DB,a.horse_id,a.asof,a.off_at,a.race),ensure_ascii=False))
if __name__=="__main__":main()
