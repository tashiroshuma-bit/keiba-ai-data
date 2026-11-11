"""V51 calibration refinement using 2025 ONLY; 2026 never selects options.

Inputs are canonical v12 and independent reviewed-race overlay. Do not use
2026 performance to fit or select temperatures. The selected calibration
is a research proposal until its 2025 chronological CV is documented.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import numpy as np

from scripts.v51_recovered_id_conditional_rank import (
    history_module, groups_for, prepared_scores, softmax, calibrate,
    stage_ce, entropy, bucket, temp_fit, save_new,
)

DB_SHA="5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd"
OVERLAY_SHA="5f80b199b61b401fb046a0d7c2fb065b8c433dbc5734fcbefb5f0740ae3d03ea"
CONF_BINS=(.1,.15,.2,.3,.4,.5,1.01)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()

def candidate(records,family):
    c=calibrate(records)
    global_temp=c["global_stage_temperatures"]["1"]
    if family=="global":
        for key,v in c["winner_entropy_confidence_groups"].items():
            v["temp"]=global_temp
    elif family=="half-shrunk-strata":
        for key,v in c["winner_entropy_confidence_groups"].items():
            v["temp"]=math.sqrt(v["temp"]*global_temp)
    elif family=="conservative-p23":
        c["global_stage_temperatures"]["2"]=1.
        c["global_stage_temperatures"]["3"]=1.
    elif family!="original-strata":
        raise ValueError("unknown calibration family")
    c["family"]=family
    return c

def metrics(records,cal):
    n=len(records)
    losses=[];briers=[];conditional2=[];conditional3=[]
    buckets={x:[] for x in CONF_BINS}
    hits=0
    for z,g in records:
        cls=bucket(softmax(z[0]))
        t=cal["winner_entropy_confidence_groups"][cls]["temp"]
        p=softmax(z[0],t)
        local=int(np.where(g["indices"]==g["first"])[0][0])
        best=int(np.argmax(p))
        hits+=int(best==local)
        losses.append(-math.log(max(float(p[local]),1e-15)))
        briers.append(float(np.square(p).sum()+1-2*p[local]))
        confidence=float(p[best])
        b=next(edge for edge in CONF_BINS if confidence<edge)
        buckets[b].append((confidence,int(best==local)))
        for st,arr in ((2,conditional2),(3,conditional3)):
            v=stage_ce(z,g,st,cal["global_stage_temperatures"][str(st)])
            if v is not None:arr.append(float(v))
    ece=sum(len(v)*abs(sum(x for x,y in v)/len(v)-sum(y for x,y in v)/len(v))
            for v in buckets.values() if v)/n
    return {"races":n,"top1_hits":hits,"top1_accuracy":hits/n,
      "winner_logloss":sum(losses)/n,"winner_brier":sum(briers)/n,
      "ece_confidence":ece,
      "conditional_second_logloss":sum(conditional2)/len(conditional2) if conditional2 else None,
      "conditional_third_logloss":sum(conditional3)/len(conditional3) if conditional3 else None}

def select(validation):
    # Winner log loss is primary, with Brier/ECE/conditional-stage safeguards.
    base=validation["global"]
    feasible=[]
    for key,v in validation.items():
        if (v["winner_brier"]<=base["winner_brier"]+.002
            and v["ece_confidence"]<=base["ece_confidence"]+.005
            and v["conditional_second_logloss"]<=base["conditional_second_logloss"]+.005
            and v["conditional_third_logloss"]<=base["conditional_third_logloss"]+.005):
            feasible.append((v["winner_logloss"],key))
    return min(feasible)[1] if feasible else "global"

def refine(db,overlay,history_script,model_path,output_dir):
    if sha(db)!=DB_SHA or sha(overlay)!=OVERLAY_SHA:
        raise ValueError("v12 canonical or verified 1975 overlay SHA mismatch")
    model=json.loads(Path(model_path).read_bytes())
    if model["canonical_db_sha256"]!=DB_SHA or model["mode"]!="full":
        raise ValueError("official recovered-ID full model required")
    hist=history_module(history_script)
    races,skipped=hist.build_dataset(db=db,overlay=overlay)
    X,rank,rids,states,years,numbers,winner=hist.create_feature_rows(races,"full")
    all_groups=groups_for(rids,rank,years,states,races)
    ordered=sorted((g for g in all_groups if g["year"]==2025 and
                    g["status"]=="validated_result"),key=lambda g:(g["date"],g["race"]))
    if len(ordered)<1000:raise ValueError("insufficient 2025 calibration races")
    # Split by DATE, never split same calendar day across fit and validation.
    dates=sorted(set(g["date"] for g in ordered))
    cutoff=dates[int(len(dates)*.7)]
    train=[g for g in ordered if g["date"]<cutoff]
    validation=[g for g in ordered if g["date"]>=cutoff]
    mean=np.asarray(model["feature_mean"],float);scale=np.asarray(model["feature_scale"],float)
    weights=np.asarray(model["stage_coefficients"],float)
    if weights.shape!=(3,31) or mean.shape!=(31,) or scale.shape!=(31,):
        raise ValueError("learned feature schema mismatch")
    standardized=(X-mean)/scale
    def records(groups):
        return [(prepared_scores(standardized,g,weights),g) for g in groups]
    train_rec=records(train)
    val_rec=records(validation)
    families=("global","original-strata","half-shrunk-strata","conservative-p23")
    cv={family:metrics(val_rec,candidate(train_rec,family)) for family in families}
    selected=select(cv)
    full_2025=records(ordered)
    final_cal=candidate(full_2025,selected)
    # 2026 is an audit only. No tuning or selection based on this section.
    holdout=[g for g in all_groups if g["year"]==2026 and g["status"]=="validated_result"]
    audit=metrics(records(holdout),final_cal)
    previous=metrics(records(holdout),model["calibration"])
    report={"schema":"jra-v51-2025-time-block-calibration-refinement-v1",
       "source_db_sha256":DB_SHA,"overlay_sha256":OVERLAY_SHA,
       "model_input_sha256":sha(model_path),
       "cv_fit_2025_races":len(train),"cv_validate_2025_races":len(validation),
       "cv_cutoff":cutoff,"cv_candidates":cv,"selected_using_2025_only":selected,
       "final_fit_all_2025_races":len(ordered),"calibration":final_cal,
       "2026_audit_not_used_to_select":audit,"2026_original_reference":previous,
       "status":"RESEARCH_CANDIDATE_NOT_ACTIVE_UNTIL_EXPLICIT_EVIDENCE_REVIEW",
       "limitations":["Winner temperature is rank-invariant; cannot raise top1 hits.",
                      "2026 previously viewed: not a pristine new prospective test.",
                      "Missing true archived future preoff feature snapshots."]}
    root=Path(output_dir)
    save_new(root/"v51_calibration_2025_cv_proposal.json",report)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--database",required=True)
    p.add_argument("--review-overlay",required=True)
    p.add_argument("--historical-feature-script",required=True)
    p.add_argument("--model",required=True)
    p.add_argument("--output-dir",required=True)
    x=p.parse_args()
    y=refine(x.database,x.review_overlay,x.historical_feature_script,x.model,x.output_dir)
    print(json.dumps({"selected":y["selected_using_2025_only"],
      "cv":y["cv_candidates"],"holdout_original":y["2026_original_reference"],
      "holdout_candidate":y["2026_audit_not_used_to_select"]},ensure_ascii=False))
