"""JRA v12 historical metadata adapter for V51 four-axis *research* ablation.

Uses previous CALENDAR DATE results only and never the target race's
finishing position, reported current weight or same-day race results.
Original JRA annual PDFs are published on the following day; when exact
publication timestamps are unavailable, this remains retrospective
research and MUST NOT create a production V51 feature snapshot.
"""
from __future__ import annotations

import collections
import json
import math
import re
import sqlite3
from pathlib import Path

import numpy as np

from scripts.v51_four_axis_preoff_research import class_level

FEATURE_NAMES=(
  "past_race_class_last3","past_rivals_prior_strength_last3",
  "prior_class_missing","prior_rival_strength_missing",
  "prior_corner4_fraction_last3","prior_early_style_last3",
  "prior_corner_finish_gain_last3","prior_style_missing",
  "jockey_track_surface_distance_residual","jockey_course_count_log",
  "jockey_condition_missing",
  "previous_reported_weight_delta_pct_last3","previous_weight_count_log",
  "previous_weight_missing"
)
GROUPS={
 "opponent_class":(0,1,2,3),
 "running_style":(4,5,6,7),
 "jockey_condition":(8,9,10),
 "previous_weight":(11,12,13)
}
CLASS_COLUMNS=(
 "race_class","class_name","race_condition","race_grade",
 "grade","class","race_name","race_title","title"
)

def _float(x):
    if isinstance(x,bool) or x is None:return None
    if type(x) in (float,int) and math.isfinite(float(x)):return float(x)
    return None

def _number(raw,*,lo=None,hi=None):
    if raw is None or isinstance(raw,bool):return None
    if isinstance(raw,(int,float)):
        if not math.isfinite(float(raw)):return None
        n=float(raw)
    elif isinstance(raw,str):
        cleaned=(raw.replace("＋","+").replace("－","-")
                    .replace("−","-").strip())
        m=re.fullmatch(r"[+-]?\d+(?:\.\d+)?",cleaned)
        if not m:return None
        n=float(cleaned)
    else:return None
    if (lo is not None and n<lo) or (hi is not None and n>hi):return None
    return n

def _parse_corner(p,field_size):
    if not isinstance(p,dict):return None
    n=int(field_size)
    for key in ("corner4_position","corner4","corner_four_position"):
        x=_number(p.get(key),lo=1,hi=n)
        if x is not None and int(x)==x:return int(x)
    # Only explicitly labelled ordered passage sequences. No guessing from finish.
    for key in ("corner_positions","passing_positions"):
        value=p.get(key)
        if isinstance(value,(list,tuple)) and 1<=len(value)<=4:
            x=_number(value[-1],lo=1,hi=n)
            if x is not None and int(x)==x:return int(x)
        if isinstance(value,str):
            cleaned=value.replace(" ","")
            if re.fullmatch(r"\d{1,2}(?:-\d{1,2}){1,3}",cleaned):
                x=int(cleaned.split("-")[-1])
                if 1<=x<=n:return x
    return None

def _parse_reported_weight(p):
    if not isinstance(p,dict):return None
    mass=_number(p.get("body_weight_raw"),lo=250,hi=700)
    delta=_number(p.get("body_weight_change_raw"),lo=-100,hi=100)
    if mass is None or delta is None or mass-delta<250 or mass-delta>700:
        return None
    return float(100*delta/(mass-delta))

def _select_metadata(conn,races):
    rcols={r[1] for r in conn.execute("pragma table_info(annual_report_races)")}
    available=[c for c in CLASS_COLUMNS if c in rcols]
    q="""select x.race_id,x.horse_number,x.payload_json,r.expected_runners"""
    if available:q+=","+",".join("r."+n for n in available)
    q+=""" from annual_report_runners x join annual_report_races r using(race_id)
       where r.status in ('validated_result','requires_review')"""
    expected={str(r) for r in races}
    source={}
    counts=collections.Counter()
    for entry in conn.execute(q):
        rid,num,payload,n=entry[:4]
        rid=str(rid)
        if rid not in expected:continue
        try:
            p=json.loads(payload or "{}")
            if not isinstance(p,dict):p={}
        except (ValueError,TypeError):p={}
        txt=next((v for v in entry[4:] if isinstance(v,str)
                  and class_level(v) is not None),None)
        if txt is None:
            for key in ("race_class","race_condition","grade","race_name"):
                if class_level(p.get(key)) is not None:
                    txt=p[key];break
        klass=class_level(txt)
        corner=_parse_corner(p,n) if type(n) is int and n>=3 else None
        weight=_parse_reported_weight(p)
        key=(rid,int(num))
        if key in source:raise ValueError("duplicate historical race/number")
        source[key]={"class_level":klass,"corner4":corner,
                     "previous_weight_delta_pct":weight}
        counts["runner_observations"]+=1
        if klass is not None:counts["class_reported"]+=1
        if corner is not None:counts["corner4_reported"]+=1
        if weight is not None:counts["weight_delta_reported"]+=1
    return source,dict(counts)

def load_source_metadata(database,races):
    c=sqlite3.connect(Path(database).resolve().as_uri()+"?mode=ro",uri=True)
    try:return _select_metadata(c,races)
    finally:c.close()

def _avg(values):
    return sum(values)/len(values) if values else None

def _feature_one(horse_history,jockey_history,track,surface,dist):
    recent=horse_history[-3:]
    klass=[r["class_level"] for r in recent if r["class_level"] is not None]
    rival=[r["rival_strength_prior"] for r in recent
           if r["rival_strength_prior"] is not None]
    corner=[r for r in recent if r["corner4"] is not None]
    corner_fracs=[(r["corner4"]-1)/(r["field_size"]-1) for r in corner]
    front=[float(q<=.33) for q in corner_fracs]
    closing=[(r["corner4"]-r["rank"])/(r["field_size"]-1) for r in corner]
    past_weights=[r["previous_weight_delta_pct"] for r in recent
                  if r["previous_weight_delta_pct"] is not None]
    # A condition-matched jockey's top3 residual is a descriptive prior only.
    valid=[r for r in jockey_history if r["rank"]>=1]
    match=[r for r in valid if r["track"]==track and r["surface"]==surface
           and abs(r["distance_m"]-dist)<=200]
    general=(sum(r["rank"]<=3 for r in valid)+20*.21)/(len(valid)+20)
             if valid else None
    cond=(sum(r["rank"]<=3 for r in match)+20*general)/(len(match)+20)
          if match else None
    return np.array([
       _avg(klass)/9 if klass else 0,
       _avg(rival) if rival else 0,
       float(not bool(klass)),float(not bool(rival)),
       _avg(corner_fracs) if corner_fracs else 0,
       _avg(front) if front else 0,
       _avg(closing) if closing else 0,
       float(not bool(corner)),
       cond-general if cond is not None else 0,
       math.log1p(len(match)),
       float(not bool(match)),
       _avg(past_weights)/10 if past_weights else 0,
       math.log1p(len(past_weights)),
       float(not bool(past_weights))
    ],dtype=np.float64)

def build_features(races,source,*,minimum_days=2):
    """Return (race_id,number) -> 14 features and coverage, no target labels."""
    if type(minimum_days) is not int or minimum_days<2:
        raise ValueError("unproven result PDFs require >=2d availability embargo")
    byday=collections.defaultdict(list)
    for rid,rows in races.items():
        if not rows:continue
        byday[rows[0]["date"]].append((str(rid),rows))
    horse_hist=collections.defaultdict(list)
    jockey_hist=collections.defaultdict(list)
    lookup={}
    counts=collections.Counter()
    # histories contain previous date results; 2-day embargo enforced below.
    import datetime as dt
    for date in sorted(byday):
        d=dt.date.fromisoformat(date)
        pending=[]
        for rid,field in byday[date]:
            n=len(field)
            statuses=[]
            for r in field:
                h=horse_hist.get(r["horse_id"],[])
                j=jockey_hist.get(r["jockey_id"],[])
                available_h=[z for z in h if (d-z["date"]).days>=minimum_days]
                available_j=[z for z in j if (d-z["date"]).days>=minimum_days]
                # Prior-rival ability is computed at the prior race, and
                # belongs only to that horse's *previous* results.
                value=_feature_one(available_h,available_j,
                                   r["track"],r["surface"],int(r["dist"]))
                key=(rid,int(r["num"]))
                if key in lookup:raise ValueError("duplicated runner in research roster")
                lookup[key]=value
                counts["feature_rows"]+=1
                if value[2]==0:counts["class_history_available"]+=1
                if value[3]==0:counts["prior_opponent_available"]+=1
                if value[7]==0:counts["prior_style_available"]+=1
                if value[10]==0:counts["jockey_condition_available"]+=1
                if value[13]==0:counts["past_weight_available"]+=1
                hh=horse_hist.get(r["horse_id"],[])
                winprior=(sum(z["rank"]==1 for z in hh
                   if (d-z["date"]).days>=minimum_days)+.56)/(
                   sum((d-z["date"]).days>=minimum_days for z in hh)+8)
                statuses.append((r,winprior))
            for r,prior in statuses:
                other=[quality for rival,quality in statuses
                       if rival["num"]!=r["num"] and
                          horse_hist.get(rival["horse_id"],[])]
                field_other=_avg(other)
                extra=source.get((rid,int(r["num"])),{})
                # Add outcomes only after the entire date's features are frozen.
                pending.append((r,extra,field_other,n,d))
        for r,extra,field_other,n,d in pending:
            row={
                "date":d,"rank":int(r["rank"]), "track":r["track"],
                "surface":r["surface"],"distance_m":int(r["dist"]),
                "field_size":n,"class_level":extra.get("class_level"),
                "corner4":extra.get("corner4"),
                "previous_weight_delta_pct":extra.get("previous_weight_delta_pct"),
                "rival_strength_prior":field_other
            }
            if r.get("horse_id"):horse_hist[r["horse_id"]].append(row)
            if r.get("jockey_id"):jockey_hist[r["jockey_id"]].append(row)
    return lookup,dict(counts)

def align_with_original(lookup,rids,numbers):
    keys=[(str(r),int(n)) for r,n in zip(rids,numbers)]
    if len(set(keys))!=len(keys):raise ValueError("duplicated aligned runner")
    missing=[key for key in keys if key not in lookup]
    if missing:
        raise ValueError(f"extended feature row alignment incomplete: {len(missing)}")
    out=np.stack([lookup[key] for key in keys])
    if out.shape!=(len(keys),len(FEATURE_NAMES)) or not np.isfinite(out).all():
        raise ValueError("nonfinite/misaligned extended research features")
    return out
