"""Real 2026-11-08 official postrace history availability for *later* V51.

Reads an immutable small JRA historical SQLite (36 races/497 runners),
never uses its final outcomes as 2026-11-08 preoff features.
Outputs counts and proof-checked *later-race historical* style/weight features,
not a model performance result or a V51 production forecast.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path

from scripts.query_jra_official_past_runs_asof import (
    DB,verify_saved_companion,parse_timestamp
)
from scripts.v51_four_axis_historical_features import _parse_corner,_number

SOURCE_RACE_DATE=dt.date(2026,11,8)

def audit(*,asof,off,db=DB,verify_sha=True):
    a=parse_timestamp(asof);o=parse_timestamp(off)
    if not a<o:raise ValueError("target race must be after forecast asof")
    if verify_sha:verify_saved_companion(db)
    c=sqlite3.connect(Path(db).resolve().as_uri()+"?mode=ro",uri=True)
    c.row_factory=sqlite3.Row
    try:
        if c.execute("pragma quick_check").fetchone()[0]!="ok":
            raise ValueError("historical source SQLite malformed")
        rows=c.execute("""select r.*,s.observed_at AS source_observed_at,
                   s.source_sha256 AS source_evidence_sha256
              from runner_postrace r join source_race s using(race)""").fetchall()
    finally:c.close()
    field_counts=Counter(x["race"] for x in rows)
    # Debugging only the public corner-notation syntax, not horse identities.
    sample_forms=list(dict.fromkeys(repr(x["corner_positions"])[:80]
                      for x in rows))[:8]
    counter=Counter()
    missing=Counter()
    style_rates=[]
    past_deltas=[]
    for x in rows:
        counter["saved_postrace_horse_rows"]+=1
        if x["source_evidence_sha256"]!=x["source_sha256"]:
            raise ValueError("JRA row and source evidence SHA mismatch")
        if x["result_only_not_prediction_feature"]!=1:
            raise ValueError("historical postrace status marker missing")
        if (o.astimezone(dt.timezone(dt.timedelta(hours=9))).date()-SOURCE_RACE_DATE).days<2:
            missing["two_calendar_day_embargo"]+=1;continue
        if parse_timestamp(x["observed_at"])>a or parse_timestamp(x["source_observed_at"])>a:
            missing["source_observed_after_target_asof"]+=1;continue
        counter["past_history_eligible_at_target_asof"]+=1
        n=field_counts[x["race"]]
        # Corner positions are parsed only from explicitly labelled fields.
        corner=_parse_corner({"passing_positions":x["corner_positions"]},n)
        if corner is not None:
            counter["previous_corner4_parsed"]+=1
            style_rates.append((corner-1)/(n-1))
        else:missing["previous_corner4_unparsed"]+=1
        w=_number(x["bodyweight_kg"],lo=250,hi=700)
        d=_number(x["bodyweight_delta_kg"],lo=-100,hi=100)
        if w is not None and d is not None and 250<=w-d<=700:
            counter["previous_weight_delta_pct_valid"]+=1
            past_deltas.append(100*float(d)/(float(w)-float(d)))
        else:missing["previous_weight_delta_unavailable"]+=1
        if x["horse_id"] is not None and str(x["horse_id"]).startswith("jra:"):
            counter["official_horse_identity_eligible"]+=1
        else:missing["unproven_horse_identity"]+=1
    return {"schema":"jra-v51-nov08-real-past-history-for-next-race-v1",
       "source_database":"operations/data_updates/jra_official_20261108_all_runner_history_v2.sqlite",
       "source_db_real_jra_races":len(field_counts),
       "asof":a.isoformat(),"target_off":o.isoformat(),
       "historical_race_date":"2026-11-08",
       "history_observed_at_proof":True,
       "minimum_calendar_lag_days":2,
       "counts":dict(counter),"missing":dict(missing),
       "corner_source_notation_samples":sample_forms,
       "mean_past_corner4_field_fraction":sum(style_rates)/len(style_rates) if style_rates else None,
       "mean_past_weight_delta_pct":sum(past_deltas)/len(past_deltas) if past_deltas else None,
       "current_race_weight_used":False,
       "same_race_result_used":False,
       "class_race_metadata_available":False,
       "jockey_official_id_available":False,
       "official_v51_model_updated":False,
       "next_race_roster_joined":False,
       "status":"REAL_SOURCE_COVERAGE_ONLY_NOT_RANK_ACCURACY",
       "limitations":["Actual publication time is not stored; original JRA capture times are used as availability bounds.",
                     "These are completed Nov8 races, not their original preoff forecasts.",
                     "No Nov14 horse roster has been joined; coverage is only potential historical features.",
                     "Class and official jockey IDs are absent from this specific small source database."]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--asof",default="2026-11-14T08:00:00+09:00")
    p.add_argument("--off",default="2026-11-14T10:00:00+09:00")
    a=p.parse_args()
    print("V51_REAL_NEXT_RACE_HISTORICAL_FEATURE_AUDIT="+json.dumps(
        audit(asof=a.asof,off=a.off),ensure_ascii=False))
if __name__=="__main__":main()
