"""Expand official JRA horse prior-run profiles to Tokyo 11R and Tokyo 12R.

Source horse IDs/URLs are EXACT links preserved from Nov8 desktop JRA result
tables (497 official runner identities). Fetch only the specified two races,
one horse at a time with throttling. Profile shows historic prior race rows:
source first observed after Nov8, so NEVER use for Nov8 backtests.
"""
from __future__ import annotations
import datetime as dt,hashlib,json,sqlite3,time
from pathlib import Path
from scripts.ingest_jra_official_kyoto12_profiles import (
    FULL,get,parse_profile,SCHEMA
)
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"operations/data_updates/jra_official_20261108_tokyo11_12_profiles_v1.sqlite"
AUDIT=ROOT/"operations/data_updates/jra_official_20261108_tokyo11_12_profiles_v1_audit.json"
SELECTED=("東京11R","東京12R")
def main():
    if OUT.exists():raise FileExistsError("already archived Tokyo profile batch")
    with sqlite3.connect(f"file:{FULL}?mode=ro",uri=True) as con:
        targets=con.execute("""SELECT DISTINCT horse_id,horse_name,horse_profile_url,race
          FROM runner_postrace WHERE race IN (?,?) ORDER BY race,horse_number""",SELECTED).fetchall()
    if not 25<=len(targets)<=36:raise ValueError("expected bounded Tokyo11+Tokyo12 runner profiles")
    found=[]
    for index,(horse_id,horse_name,url,race) in enumerate(targets):
        if index:time.sleep(1)
        try:
            raw=get(url)
            past=parse_profile(raw,horse_name)
            found.append({"race":race,"horse_id":horse_id,"horse_name":horse_name,
                "url":url,"source_sha256":hashlib.sha256(raw).hexdigest(),
                "observed_at":dt.datetime.now(dt.timezone.utc).isoformat(),
                "past":past,"status":"verified"})
        except Exception as exc:
            found.append({"race":race,"horse_id":horse_id,"horse_name":horse_name,
                "url":url,"error":str(exc)[:300],"status":"rejected"})
    valid=[x for x in found if x["status"]=="verified"]
    if len(valid)<len(targets)-3:raise ValueError("insufficient verified profiles")
    OUT.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(OUT)
    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.executescript(SCHEMA)
        for x in found:
            if x["status"]!="verified":
                con.execute("INSERT INTO unavailable_profile VALUES(?,?,?,?)",
                    (x["horse_id"],x["horse_name"],x["url"],x["error"]))
                continue
            con.execute("INSERT INTO official_profile VALUES(?,?,?,?,?,0,0,?)",
                (x["horse_id"],x["horse_name"],x["url"],x["source_sha256"],
                 x["observed_at"],len(x["past"])))
            for h in x["past"]:
                con.execute("""INSERT OR IGNORE INTO official_past_run VALUES(
                     ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                   (x["horse_id"],h["prior_race_date"],h["venue"],
                    h["race_name"],h["distance_surface"],h["going"],
                    h["field_size"],h["popularity_final"],h["finish_position"],
                    h["jockey_name"],h["assigned_weight_kg"],h["bodyweight_kg"],
                    h["time_text"],h["rating_text"],h["opponent_text"],
                    x["observed_at"],x["source_sha256"]))
        meta={"batch":"tokyo11_tokyo12_2026-11-08",
            "first_observed_after_target_race":"true",
            "allow_20261108_preoff_backtest":"false",
            "future_after_observation_only":"true",
            "past_result_original_publish_time":"not_verified",
            "horse_identity":"official_JRA_profile_href"}
        for k,v in meta.items():con.execute("INSERT INTO meta VALUES(?,?)",(k,v))
        con.commit()
        if con.execute("PRAGMA integrity_check").fetchone()[0]!="ok" or con.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("new profile SQLite invalid")
        count=con.execute("SELECT count(*) FROM official_past_run").fetchone()[0]
        names=con.execute("SELECT count(*) FROM official_profile").fetchone()[0]
    finally:con.close()
    audit={"schema":"jra-official-verified-tokyo11-12-profile-batch-v1",
        "races":list(SELECTED),
        "attempted_profiles":len(targets),"verified_profiles":names,
        "unavailable_profiles":len(targets)-names,
        "past_run_rows":count,
        "sha256":hashlib.sha256(OUT.read_bytes()).hexdigest(),
        "sqlite_bytes":OUT.stat().st_size,
        "postrace_observed_only":True,
        "eligible_for_2026_11_08_retrospective_preoff":False,
        "eligible_for_future_after_observation":True,
        "public_time_of_original_past_run_unverified":True,
        "official_horse_id_join_proof":True,
        "failures":[{k:r[k] for k in ("race","horse_id","error")} for r in found if r["status"]=="rejected"]}
    AUDIT.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(audit,ensure_ascii=False))
if __name__=="__main__":main()
