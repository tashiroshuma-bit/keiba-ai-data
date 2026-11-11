"""Read-only canonical JRA v12 audit for V51 four-axis feature availability.

A post-race PDF may contain race-class, corner positions or weight change.
That alone does NOT provide a timestamped pre-race training observation.
No official v51 coefficient update and no result-PDF current-weight leakage.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sqlite3
from pathlib import Path

from scripts.v51_four_axis_preoff_research import class_level

V12_SHA="5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd"
CLASS_COLS=("race_class","class_name","race_condition","race_grade",
            "grade","class","race_name","race_title","title")
CORNER_KEYS=("corner4_position","corner4","corner_positions",
             "passing_positions","corner_passages","corner_order")
WEIGHT_KEYS=("body_weight_raw","body_weight_change_raw")
AVAILABLE_FUTURE_SOURCES=("racecard_preoff","bodyweight_announced_preoff")

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for data in iter(lambda:f.read(1<<20),b""):h.update(data)
    return h.hexdigest()

def table_columns(conn,table):
    return [r[1] for r in conn.execute(f"pragma table_info({table})")]

def field_audit(conn,*,max_runners=None):
    tables={r[0] for r in conn.execute(
        "select name from sqlite_master where type='table'")}
    required={"annual_report_races","annual_report_runners"}
    if not required<=tables:raise ValueError("canonical annual result tables missing")
    rc=table_columns(conn,"annual_report_races")
    hc=table_columns(conn,"annual_report_runners")
    for k in ("race_id","race_date","status","track","surface","distance_m"):
        if k not in rc:raise ValueError("canonical races column absent: "+k)
    for k in ("race_id","horse_number","horse_id","jockey_id","payload_json"):
        if k not in hc:raise ValueError("canonical runners column absent: "+k)

    possible_class=[c for c in CLASS_COLS if c in rc]
    selection=["r."+c for c in possible_class]
    stmt="""select r.race_date, r.race_id, r.status,
       r.track, r.surface, r.distance_m,
       x.horse_number, x.horse_id, x.jockey_id, x.payload_json"""
    if selection:stmt+=", "+", ".join(selection)
    stmt+=" from annual_report_runners x join annual_report_races r on x.race_id=r.race_id where r.status='validated_result' order by r.race_date, r.race_id,x.horse_number"
    if max_runners is not None:
        if type(max_runners) is not int or max_runners<=0:raise ValueError("bad row limit")
        stmt+=" limit "+str(max_runners)
    count=0
    race_ids=set()
    years=collections.Counter()
    keys=collections.Counter()
    usable=collections.Counter()
    seen_horse=set();seen_jockey=set()
    today_horse=set();today_jockey=set()
    day=None
    for fields in conn.execute(stmt):
        date,rid,status,track,surface,dist,num,hid,jid,raw=fields[:10]
        extra=fields[10:]
        if day!=date:
            seen_horse.update(today_horse);seen_jockey.update(today_jockey)
            today_horse.clear();today_jockey.clear()
            day=date
        count+=1
        race_ids.add(rid)
        years[str(date)[:4]]+=1
        if hid:
            usable["verified_horse_id_present"]+=1
            if hid in seen_horse:usable["previous_calendar_day_horse_start"]+=1
            today_horse.add(hid)
        if jid:
            usable["jockey_id_present"]+=1
            if jid in seen_jockey:usable["previous_calendar_day_jockey_start"]+=1
            today_jockey.add(jid)
        try:
            p=json.loads(raw) if raw else {}
        except (TypeError,ValueError):
            usable["invalid_payload_json"]+=1
            p={}
        if not isinstance(p,dict):
            usable["non_mapping_payload"]+=1
            p={}
        keys.update(p.keys())
        if any(p.get(k) not in (None,"","-","－") for k in CORNER_KEYS):
            usable["runner_corner_related_payload_present"]+=1
        if p.get("body_weight_raw") not in (None,"","-","－"):
            usable["postrace_weight_reported"]+=1
        if p.get("body_weight_change_raw") not in (None,"","-","－"):
            usable["postrace_delta_reported"]+=1
        if any(class_level(str(v)) is not None for v in extra if v is not None):
            usable["race_class_label_present_in_race_columns"]+=1
        if "published_at" in p and "observed_at" in p:
            usable["generic_published_and_observed_fields_present"]+=1

    if not count:raise ValueError("no JRA validated-result rows")
    return {
       "schema":"jra-v51-four-axis-canonical-source-coverage-v1",
       "n_validated_runner_rows_scanned":count,
       "distinct_races_scanned":len(race_ids),
       "year_runner_counts":dict(years),
       "runner_payload_fields":dict(keys.most_common(70)),
       "race_class_column_candidates":possible_class,
       "source_coverage_counts":dict(usable),
       "research_previous_date_identity_coverage_only":True,
       "preoff_class_observation_count_proven":None,
       "preoff_corner_position_count_proven":None,
       "preoff_current_bodyweight_count_proven":None,
       "official_v51_model_changed":False,
       "limits":[
         "Bodyweight fields in historical RESULT PDFs cannot prove pre-race announcement timestamps.",
         "Corner positions from historical results may serve as NEXT-race history only.",
         "Class strings may appear in outcome reports but require preoff card or historical source evidence before model activation.",
         "Past-race eligibility for research uses previous-day rule, not proof of publication time.",
         "This audit checks only source field coverage, not predictive uplift."
       ]
    }

def run(path,*,max_runners=None,strict_v12=True):
    file=Path(path)
    digest=sha256(file)
    if strict_v12 and digest!=V12_SHA:
        raise ValueError("must use canonical v12 source SHA256")
    conn=sqlite3.connect(file.resolve().as_uri()+"?mode=ro",uri=True)
    try:
        check=conn.execute("pragma quick_check").fetchone()[0]
        if check!="ok":raise ValueError("SQLite consistency check failed")
        out=field_audit(conn,max_runners=max_runners)
    finally:conn.close()
    out.update({"source_database_sha256":digest,"source_database_bytes":file.stat().st_size,
      "sqlite_quick_check":"ok","sample_limit":max_runners,
      "is_exact_canonical_v12_source":digest==V12_SHA})
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--database",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--max-runners",type=int)
    p.add_argument("--allow-noncanonical-research",action="store_true")
    a=p.parse_args()
    result=run(a.database,max_runners=a.max_runners,
               strict_v12=not a.allow_noncanonical_research)
    target=Path(a.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("x",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
        f.write("\n")
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":main()
