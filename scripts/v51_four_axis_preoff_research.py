"""Verified pre-off V51 research features: rival class, running style, rider and bodyweight.

This module produces *research-only* inputs alongside the official 31 features.
It never modifies the live V51 weights or fills missing values with fabricated
post-race data. No "day+1" availability assumptions are accepted here.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from typing import Any

from scripts.v51_preoff_provenance_guard import (
    check_historical_observation, strict_time
)

JRA_BASE="https://www.jra.go.jp/"
CLASS_SCALE={
    "newcomer":0,"maiden":1,"one_win":2,"two_win":3,"three_win":4,
    "open":5,"listed":6,"g3":7,"g2":8,"g1":9
}
# Higher priority before lower, so G1 does not parse as 1-win.
CLASS_RULES=(
    (r"G\s*(?:Ⅰ|I\b|1\b|Ｉ)|GI\b|ＧⅠ", "g1"),
    (r"G\s*(?:Ⅱ|II\b|2\b|ＩＩ)|GII\b|ＧⅡ", "g2"),
    (r"G\s*(?:Ⅲ|III\b|3\b|ＩＩＩ)|GIII\b|ＧⅢ", "g3"),
    (r"リステッド|\bLISTED\b|(?:^|\W)L\s*(?:競走|レース)", "listed"),
    (r"オープン|\bOP\b|OPEN", "open"),
    (r"3勝クラス|３勝クラス|1600万円以下|1600万下", "three_win"),
    (r"2勝クラス|２勝クラス|1000万円以下|1000万下", "two_win"),
    (r"1勝クラス|１勝クラス|500万円以下|500万下", "one_win"),
    (r"未勝利", "maiden"),
    (r"新馬|メイクデビュー", "newcomer")
)

def as_float(x: Any, lo: float, hi: float) -> float | None:
    if isinstance(x,bool) or not isinstance(x,(int,float)):
        return None
    x=float(x)
    return x if math.isfinite(x) and lo<=x<=hi else None

def iso_valid_timestamp(value):
    if not isinstance(value,str) or not value:
        raise ValueError("verified timezone-aware timestamp required")
    return strict_time(value)

def class_level(text):
    """Recognize explicit JRA class wording, not a guessed class by race name."""
    if not isinstance(text,str) or not text.strip():
        return None
    for pattern,key in CLASS_RULES:
        if re.search(pattern,text,flags=re.I):
            return CLASS_SCALE[key]
    return None

def verified_class(klass,proof,asof,off):
    if klass is None:return None
    if not isinstance(proof,dict):
        raise ValueError("race class requires authenticated preoff class proof")
    _proof(proof,asof,off,need_published=False)
    value=class_level(klass)
    if value is None:
        return None
    return value

def _proof(proof,asof,off,*,need_published):
    if not isinstance(proof,dict):raise ValueError("source proof dictionary required")
    u=str(proof.get("source_url",""))
    sha=str(proof.get("source_sha256",""))
    if not u.startswith(JRA_BASE) or len(sha)!=64 or any(
            c not in "0123456789abcdef" for c in sha.lower()):
        raise ValueError("official JRA source URL and SHA256 required")
    if not proof.get("observed_at"):
        raise ValueError("source observation timestamp required")
    captured=iso_valid_timestamp(proof["observed_at"])
    if captured>asof or asof>=off:
        raise ValueError("post-asof observation or post-race forecast")
    if need_published:
        if not proof.get("published_at"):
            raise ValueError("actual published_at timestamp required")
        publication=iso_valid_timestamp(proof["published_at"])
        if publication>captured or publication>asof:
            raise ValueError("post-asof publication or impossible chronology")
        if proof.get("availability_basis") in (
            "assumed_calendar_day_lag_for_research_only",
            "postrace_pdf_metadata","unknown"):
            raise ValueError("unverified result publication timestamp")
    return captured

def _history(rows,horse_id,jockey_id,asof,off,kind):
    if not isinstance(rows,list):raise ValueError("history must be a list")
    result=[]
    seen=set()
    for r in rows:
        if not isinstance(r,dict):raise ValueError("bad historical entry")
        if kind=="horse" and r.get("horse_id")!=horse_id:
            raise ValueError("past horse identity mismatch")
        if kind=="jockey" and r.get("jockey_id")!=jockey_id:
            raise ValueError("past jockey identity mismatch")
        check_historical_observation(
            r, race_off_at=off.isoformat(),forecast_asof=asof.isoformat())
        key=(r.get("race_id"),r.get("horse_id"),r.get("jockey_id"))
        if key in seen:raise ValueError("duplicated prior race identity")
        seen.add(key)
        result.append(r)
    return sorted(result,key=lambda x:iso_valid_timestamp(x["off_at"]))

def _prev_finish(r):
    n=r.get("field_size")
    pos=r.get("finish_order")
    if type(n) is not int or type(pos) is not int or n<3 or not 1<=pos<=n:
        return None
    return (n-pos)/(n-1)

def _corner_style(r):
    n=r.get("field_size")
    pos=r.get("corner4_position")
    if type(n) is not int or type(pos) is not int or n<3 or not 1<=pos<=n:
        return None
    q=(pos-1)/(n-1)
    if q<=0.15:return "front"
    if q<=0.33:return "prominent"
    if q<=0.67:return "midfield"
    return "closer"

def _mean(xs):
    return sum(xs)/len(xs) if xs else None

def _last_n(rows,n):
    return rows[-n:]

def _historical_weight_fraction(r):
    weight=as_float(r.get("body_weight_kg"),250,700)
    delta=as_float(r.get("body_weight_change_kg"),-100,100)
    if weight is None or delta is None or not 250<=weight-delta<=700:
        return None
    return 100.0*delta/(weight-delta)

def _rider_condition_stats(hist,track,surface,distance_m):
    eligible=[]
    for r in hist:
        if r.get("track")!=track or r.get("surface")!=surface:
            continue
        d=r.get("distance_m")
        if type(d) is not int or abs(d-distance_m)>200:
            continue
        if _prev_finish(r) is not None:
            eligible.append(r)
    overall=[r for r in hist if _prev_finish(r) is not None]
    if not overall:
        return {"jockey_condition_starts":0,"jockey_condition_top3":None,
                "jockey_condition_residual":None,"jockey_global_top3":None}
    # Explicit shrinkage: twenty reference pseudo starts with 21% top-3 rate.
    p0=0.21
    global_p=(sum(r["finish_order"]<=3 for r in overall)+20*p0)/(len(overall)+20)
    if not eligible:
        return {"jockey_condition_starts":0,"jockey_condition_top3":None,
                "jockey_condition_residual":None,"jockey_global_top3":global_p}
    cond=(sum(r["finish_order"]<=3 for r in eligible)+20*global_p)/(len(eligible)+20)
    return {"jockey_condition_starts":len(eligible),
            "jockey_condition_top3":cond,
            "jockey_condition_residual":cond-global_p,
            "jockey_global_top3":global_p}

def bodyweight_announcement(announcement,horse_id,asof,off):
    """Only original JRA announced race-day weight, never result-PDF weight."""
    missing={"bodyweight_pct":None,"bodyweight_kg":None,
             "bodyweight_change_kg":None,"bodyweight_available":False,
             "bodyweight_missing_reason":"not_announced_or_no_verified_snapshot"}
    if announcement is None:return missing
    if not isinstance(announcement,dict):
        raise ValueError("invalid bodyweight announcement")
    if announcement.get("horse_id")!=horse_id:
        raise ValueError("bodyweight announcement horse ID mismatch")
    if announcement.get("status")!="発表済":
        return missing
    _proof(announcement,asof,off,need_published=True)
    w=as_float(announcement.get("bodyweight_kg"),250,700)
    d=as_float(announcement.get("bodyweight_change_kg"),-100,100)
    if w is None or d is None or not 250<=w-d<=700:
        raise ValueError("announced bodyweight requires valid measured kg and change")
    return {"bodyweight_pct":100*d/(w-d),"bodyweight_kg":w,
            "bodyweight_change_kg":d,"bodyweight_available":True,
            "bodyweight_missing_reason":None}

def runner_features(runner,*,asof,off,track,surface,distance_m,
                    current_class=None,current_class_proof=None):
    if not isinstance(runner,dict):
        raise ValueError("runner dictionary required")
    if not (asof<off):raise ValueError("forecast must be before race")
    horse_id=runner.get("horse_id")
    jockey_id=runner.get("jockey_id")
    proof=runner.get("official_identity_proof")
    if horse_id:
        if not isinstance(proof,dict) or proof.get("horse_id")!=horse_id:
            raise ValueError("JRA identity proof required before joining past races")
        _proof(proof,asof,off,need_published=False)
    elif runner.get("horse_history"):
        raise ValueError("unverified horse identity cannot join history")
    history=_history(runner.get("horse_history",[]),horse_id,jockey_id,
                     asof,off,"horse") if horse_id else []
    rider=_history(runner.get("jockey_history",[]),horse_id,jockey_id,
                   asof,off,"jockey") if jockey_id else []
    cur=verified_class(current_class,current_class_proof,asof,off)
    recent=_last_n(history,3)
    classes=[class_level(x.get("race_class")) for x in recent]
    valid_class=[x for x in classes if x is not None]
    last_class=next((x for x in reversed(classes) if x is not None),None)
    past_rival=[as_float(x.get("opponent_strength_preoff"),0,1) for x in recent
                if x.get("opponent_strength_basis")=="preoff_prior_runner_histories"]
    past_rival=[x for x in past_rival if x is not None]
    corner=[_corner_style(x) for x in recent]
    available_styles=[x for x in corner if x is not None]
    # Position normalized 0 = leading, 1 = rearmost.
    corner_frac=[(x["corner4_position"]-1)/(x["field_size"]-1)
                 for x in recent if _corner_style(x) is not None]
    previous_weight=[_historical_weight_fraction(x) for x in recent]
    previous_weight=[x for x in previous_weight if x is not None]
    rider_stats=_rider_condition_stats(rider,track,surface,distance_m)
    row={
        "horse_id":horse_id,
        "class_strength_last3":_mean(valid_class),
        "class_strength_observed_races":len(valid_class),
        "class_change_from_last":cur-last_class
             if cur is not None and last_class is not None else None,
        "rivals_preoff_strength_last3":_mean(past_rival),
        "rivals_strength_observed_races":len(past_rival),
        "corner4_position_last3":_mean(corner_frac),
        "style_front_or_prominent_rate":(
            sum(x in ("front","prominent") for x in available_styles)/
            len(available_styles) if available_styles else None),
        "style_closer_rate":(
            sum(x=="closer" for x in available_styles)/len(available_styles)
            if available_styles else None),
        "style_observed_races":len(available_styles),
        "previous_bodyweight_pct_last3":_mean(previous_weight),
        "previous_bodyweight_observed_races":len(previous_weight),
        "prior_horse_starts":len(history),
        "prior_jockey_starts":len(rider),
    }
    row.update(rider_stats)
    row.update(bodyweight_announcement(runner.get("bodyweight_announcement"),
                                       horse_id,asof,off))
    return row

def build(runners,*,forecast_asof,race_off_at,track,surface,distance_m,
          current_class=None,current_class_proof=None):
    asof=iso_valid_timestamp(forecast_asof)
    off=iso_valid_timestamp(race_off_at)
    if not asof<off:
        raise ValueError("race has already started")
    if type(distance_m) is not int or not 800<=distance_m<=4200:
        raise ValueError("invalid flat distance")
    if not isinstance(runners,list) or len(runners)<3:
        raise ValueError("full non-obstacle field required")
    numbers=[r.get("number") for r in runners]
    if any(type(n) is not int or n<1 for n in numbers) or len(numbers)!=len(set(numbers)):
        raise ValueError("duplicate/invalid horse numbers")
    ids=[r.get("horse_id") for r in runners if r.get("horse_id")]
    if len(ids)!=len(set(ids)):raise ValueError("duplicate JRA horse IDs")
    output=[{"number":r["number"],
             **runner_features(r,asof=asof,off=off,track=track,
                surface=surface,distance_m=distance_m,
                current_class=current_class,current_class_proof=current_class_proof)}
            for r in runners]
    return {"schema":"jra-v51-four-axis-preoff-research-v1",
      "production_model_updated":False,
      "asof":asof.isoformat(),"race_off":off.isoformat(),
      "runners":output,
      "sources":"official original JRA timestamps and prior published result only",
      "limitations":["Current bodyweight is absent until actually announced and observed before asof",
         "No race-result-pdf weights may be relabeled as race-day preoff announcements",
         "Historical opponent strengths require prior-field-only derivation proof",
         "Candidate feature vectors have not yet been trained or independently validated"]}
