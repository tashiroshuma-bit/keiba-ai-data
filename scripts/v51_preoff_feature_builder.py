"""Exploratory point-in-time six-axis features for v51 without model changes.

Accepts externally authenticated, *observed by asof* past result rows. This
does not authenticate historical publication itself and must not be treated
as evidence that all historical PDFs were publicly available in real time.
No actual horse IDs are guessed and no live production probabilities changed.
"""
import datetime as dt
import math
from collections import defaultdict
try:
    from scripts.v51_research_diagnostics import when, safe, audit_identity_field
except ModuleNotFoundError:
    from v51_research_diagnostics import when, safe, audit_identity_field

def mean(seq):
    return sum(seq)/len(seq) if seq else None

def normfinish(row):
    n=row["field_size"];finish=row["finish_order"]
    if type(n) is not int or type(finish) is not int or n<3 or not 1<=finish<=n:
        raise ValueError("bad historical field / rank")
    return (n-finish)/(n-1)

def history_cutoff(history,asof,off,*,horse_id=None):
    out=[]
    for x in history:
        if not x.get("observed_at") or not x.get("off_at"):
            raise ValueError("historical observation metadata required")
        if when(x["off_at"])>=when(off) or when(x["observed_at"])>when(asof):
            raise ValueError("historical future information detected")
        if horse_id is not None and x.get("horse_id")!=horse_id:
            raise ValueError("cross-horse join forbidden")
        if not x.get("source_sha256") or not x.get("source_url"):
            raise ValueError("historical original source provenance missing")
        out.append(x)
    return sorted(out,key=lambda x:when(x["off_at"]))

def runner_history_features(h,asof,off,track,surface,distance,class_index):
    hid=h.get("horse_id")
    # No proven official identity => no history joins, never impute 0.
    if not h.get("identity_evidence") or not hid:
        return {"horse_form_recent3":None,"horse_form_starts":0,"class_change":None,
                "recent_opponent_quality":None,"jockey_course_distance":None,
                "rest_days":None,"bodyweight_change_percent":None,
                "age_years":h.get("age_years")}
    hist=history_cutoff(h.get("horse_history",[]),asof,off,horse_id=hid)
    recent=hist[-3:]
    form=mean([normfinish(x) for x in recent])
    class_past=recent[-1].get("class_index") if recent else None
    if class_past is not None:class_past=safe(class_past)
    opponent=mean([safe(x["opponent_strength"]) for x in recent
                   if x.get("opponent_strength") is not None])
    rider_hist=history_cutoff(h.get("jockey_history",[]),asof,off)
    matched=[x for x in rider_hist if x.get("jockey_id")==h.get("jockey_id")
             and x.get("track")==track and x.get("surface")==surface
             and abs(int(x.get("distance_m",0))-int(distance))<=200]
    # Shrink observed rider effect toward neutral .5, with n+20 denominator
    rider=(sum(normfinish(x)-0.5 for x in matched)/(len(matched)+20)
           if matched else None)
    last_off=when(hist[-1]["off_at"]) if hist else None
    rest_days=(when(off)-last_off).days if last_off else None
    current_weight=h.get("body_weight_kg")
    change=h.get("body_weight_change_kg")
    # Horse mass change is only valid with announced current mass and exact preoff observation
    if (current_weight is not None or change is not None):
        if h.get("weight_observed_at") is None or when(h["weight_observed_at"])>when(asof):
            raise ValueError("current horse bodyweight is only observed after forecast")
    percent=None
    if current_weight is not None and change is not None:
        body=safe(current_weight);delta=safe(change)
        if body is None or delta is None or not 250<=body<=700 or body-delta<=0:
            raise ValueError("invalid announced body weight")
        percent=100*delta/(body-delta)
    return {"horse_form_recent3":form,"horse_form_starts":len(hist),
            "class_change":safe(class_index)-class_past if class_past is not None else None,
            "recent_opponent_quality":opponent,
            "jockey_course_distance":rider,"jockey_course_distance_starts":len(matched),
            "rest_days":rest_days,"bodyweight_change_percent":percent,
            "age_years":h.get("age_years")}

def day_bias(previous_day_races,asof,off,track,surface):
    scores={"early":[],"other":[],"inside":[],"outside":[]}
    for race in previous_day_races:
        if race.get("track")!=track or race.get("surface")!=surface:continue
        if when(race["off_at"])>=when(off) or when(race["observed_at"])>when(asof):
            raise ValueError("future same-day result used for track bias")
        if when(race["off_at"]).date()!=when(off).date():continue
        for h in race.get("horses",[]):
            score=normfinish(h)
            n=h["field_size"]
            corner=h.get("corner4_position")
            if type(corner) is int and 1<=corner<=n:
                scores["early" if corner<=max(1,n//3) else "other"].append(score)
            gate=h.get("gate_number")
            if type(gate) is int and 1<=gate<=n:
                scores["inside" if gate<=max(1,n//2) else "outside"].append(score)
    early=mean(scores["early"]);other=mean(scores["other"])
    inside=mean(scores["inside"]);outside=mean(scores["outside"])
    return {"pace_advantage":early-other if early is not None and other is not None else None,
            "inside_outside_advantage":inside-outside if inside is not None and outside is not None else None,
            "evidence_horses":sum(len(s) for s in scores.values())//2,
            "status":"DESCRIPTIVE_PREOFF_EARLIER_RACES_ONLY"}

def build(runners,*,asof,off,track,surface,distance_m,class_index,prior_day_results=()):
    identity=audit_identity_field(runners,asof,off)
    if len({h.get("jockey_id") for h in runners if h.get("jockey_id")})!=sum(bool(h.get("jockey_id")) for h in runners):
        raise ValueError("jockey appears multiple times in same race")
    for h in runners:
        if h.get("horse_id") and not h.get("identity_evidence"):
            raise ValueError("unproven horse ID")
    features={}
    for h in runners:
        features[h["number"]]=runner_history_features(
            h,asof,off,track,surface,distance_m,class_index)
    # Field average of *other horses*, never today's finishing order.
    for number,item in features.items():
        rivals=[f["horse_form_recent3"] for no,f in features.items()
                if no!=number and f["horse_form_recent3"] is not None]
        item["rivals_recent_form"]=mean(rivals)
        item["relative_recent_form"]=(item["horse_form_recent3"]-mean(rivals)
              if item["horse_form_recent3"] is not None and rivals else None)
    day=day_bias(prior_day_results,asof,off,track,surface)
    return {"schema":"v51-preoff-feature-builder-v1",
            "status":"UNFITTED_RESEARCH_FEATURES_ONLY",
            "asof":asof,"off":off,"identity_coverage":identity,
            "day_bias":day,
            "runners":[{"number":h["number"],**features[h["number"]]} for h in runners],
            "model_fit_complete":False,"v50_modified":False}
