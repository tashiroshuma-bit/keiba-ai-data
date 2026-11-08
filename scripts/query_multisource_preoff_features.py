"""Select only proven point-in-time external features for V50/V51 shadow.

Does not alter prediction rankings. Explicit same-source timestamp, same
official horse IDs, no late source publications and no post-race final odds.
"""
from __future__ import annotations
import datetime as dt,json,sqlite3
from pathlib import Path

def parse(s):
    v=dt.datetime.fromisoformat(str(s).replace("Z","+00:00"))
    if v.tzinfo is None:raise ValueError("timezone evidence missing")
    return v

def export_asof(database,race_id,forecast_asof,original_off_at,official_horses):
    asof=parse(forecast_asof);off=parse(original_off_at)
    if not asof<off:raise ValueError("forecast must be earlier than original off")
    roster={int(h["number"]):h["horse_id"] for h in official_horses}
    if not roster or len(roster)!=len(official_horses) or any(
        not str(x).startswith("jra:") for x in roster.values()):
        raise ValueError("complete verified official ID roster required")
    c=sqlite3.connect(f"file:{Path(database)}?mode=ro",uri=True)
    try:
        records=c.execute("""SELECT horse_number,verified_jra_horse_id,feature_key,
             value_text,value_num,source_id,observed_at,published_at,off_at,
             source_url,source_sha256 FROM multi_source_observation
             WHERE official_race_id=? AND usable_for_v50_v51_preoff=1""",(race_id,)).fetchall()
    finally:c.close()
    candidates={}
    rejected=0
    for n,hid,key,text,num,source,observed,published,source_off,url,sha in records:
        if n not in roster or roster[n]!=hid:
            rejected+=1;continue
        if (not published or not source_off or
            not(parse(published)<=parse(observed)<=asof<parse(source_off)) or
            parse(source_off)!=off):
            rejected+=1;continue
        row={"horse_number":n,"horse_id":hid,"feature_key":key,
            "value":num if num is not None else text,
            "source":source,"source_url":url,"source_sha256":sha,
            "published_at":published,"observed_at":observed}
        k=(n,key)
        # With equally grounded updates the newest PREOFF observation wins.
        if k not in candidates or parse(observed)>parse(candidates[k]["observed_at"]):
            candidates[k]=row
    return {"race_id":race_id,"asof":forecast_asof,
      "off_at":original_off_at,"field_size":len(roster),
      "usable_external_fields":list(candidates.values()),"rejected_records":rejected,
      "ranking_or_v50_probabilities_modified":False,
      "no_final_odds_or_late_publication":True}
