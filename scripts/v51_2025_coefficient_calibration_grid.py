"""V51 exact-v12, leakage-aware coefficient and calibration study.

Uses 2023-24 trained, frozen stage coefficients. 2025 dates split into
calibration fit (first 40%), candidate search (next 40%) and untouched
within-study temporal acceptance (final 20%). 2026 is an audit ONLY.
No current bodyweight available among the 31 verified as-of features.
No changes to standard_v51_model.json or official future forecasts.
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from scripts.v51_recovered_id_conditional_rank import (
    history_module, groups_for, prepared_scores, softmax, save_new, bucket
)
from scripts.v51_calibration_refinement import candidate, metrics, select, DB_SHA, OVERLAY_SHA

# Disjoint groups of the 31 canonical features. Never assign bodyweight.
GROUPS = {
    "recent_form": (8,9,10,11,12,13),
    "horse_course_distance": (14,15,16,17,18,19),
    "jockey_history": (20,21,22,23,24,25,26),
    "field_relative_strength": (27,28,29,30),
}
FACTORS = (0.0, 0.5, 0.75, 1.0, 1.25, 1.5)
CALIBRATION_FAMILIES = (
    "global", "original-strata", "half-shrunk-strata", "conservative-p23"
)


def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(2**20),b""):
            h.update(block)
    return h.hexdigest()


def validate_source(database,overlay,history_script,model_path):
    if file_sha(database)!=DB_SHA or file_sha(overlay)!=OVERLAY_SHA:
        raise ValueError("authenticated JRA v12 DB or review sidecar SHA mismatch")
    model=json.loads(Path(model_path).read_bytes())
    hist=history_module(history_script)
    if (model.get("mode")!="full" or model.get("feature_count")!=31 or
        model.get("canonical_db_sha256")!=DB_SHA or
        list(model.get("feature_names",[]))!=list(hist.FEATURES)):
        raise ValueError("official v51 fixed 31-feature schema required")
    mean=np.asarray(model["feature_mean"],dtype=float)
    scale=np.asarray(model["feature_scale"],dtype=float)
    weights=np.asarray(model["stage_coefficients"],dtype=float)
    if (mean.shape!=(31,) or scale.shape!=(31,) or weights.shape!=(3,31)
        or not np.isfinite(mean).all() or not np.isfinite(scale).all()
        or not np.isfinite(weights).all() or np.any(scale<=0)):
        raise ValueError("nonfinite or incompatible frozen model")
    return model,hist,mean,scale,weights


def make_splits(groups):
    ordered=sorted((g for g in groups
        if g["year"]==2025 and g["status"]=="validated_result"),
        key=lambda g:(g["date"],g["race"]))
    dates=sorted({g["date"] for g in ordered})
    if len(dates)<70 or len(ordered)<2000:
        raise ValueError("insufficient real 2025 JRA race-date folds")
    a=dates[int(len(dates)*0.4)]
    b=dates[int(len(dates)*0.8)]
    fit=[g for g in ordered if g["date"]<a]
    search=[g for g in ordered if a<=g["date"]<b]
    confirm=[g for g in ordered if g["date"]>=b]
    if min(len(fit),len(search),len(confirm))<350:
        raise ValueError("insufficient independent time-split cohort")
    return fit,search,confirm,{"fit_before":a,"search_before":b,
        "fit_races":len(fit),"search_races":len(search),"confirm_races":len(confirm),
        "all_2025_races":len(ordered),"unique_2025_dates":len(dates)}


def scale_stage1(weights,group=None,factor=1.0):
    w=weights.copy()
    if group is not None:
        if group not in GROUPS:raise ValueError("unknown official feature group")
        if factor not in FACTORS:raise ValueError("out-of-grid coefficient scale")
        w[0,list(GROUPS[group])]*=factor
    return w


def record_scores(standardized,groups,weights):
    return [(prepared_scores(standardized,g,weights),g) for g in groups]


def evaluate_group(records,cal):
    result=metrics(records,cal)
    if not all(math.isfinite(result[k]) for k in
        ("winner_logloss","winner_brier","ece_confidence",
         "conditional_second_logloss","conditional_third_logloss")):
        raise ValueError("invalid calibration metric")
    return result


def choice_for_family(search_scores):
    # Configured selection sees 2025 search only; no 2026 or final 2025.
    return select(search_scores)


def coefficient_choice(search_scores,base):
    # Main objective: winner hits (temperature alone cannot change the ranking).
    # Prevent a high-hit but catastrophically uncalibrated option.
    feasible=[]
    for name,score in search_scores.items():
        if (score["winner_logloss"] <= base["winner_logloss"]+0.025
            and score["winner_brier"] <= base["winner_brier"]+0.015
            and score["ece_confidence"] <= base["ece_confidence"]+0.03):
            feasible.append(( -score["top1_accuracy"],
                score["winner_logloss"], name))
    return min(feasible)[2] if feasible else "original"


def winner_by_date(records,cal):
    out=collections.defaultdict(list)
    for z,g in records:
        cls=bucket(softmax(z[0]))
        t=cal["winner_entropy_confidence_groups"][cls]["temp"]
        probs=softmax(z[0],t)
        original_indices=g["indices"]
        true_local=int(np.where(original_indices==g["first"])[0][0])
        out[g["date"]].append(int(int(np.argmax(probs))==true_local))
    return out


def bootstrap_paired_hits(a,b,seed=20261111,repetitions=2000):
    aa=winner_by_date(*a);bb=winner_by_date(*b)
    if sorted(aa)!=sorted(bb):raise ValueError("different date folds")
    days=sorted(aa)
    if any(len(aa[d])!=len(bb[d]) for d in days):
        raise ValueError("different race denominators")
    diff={d:np.asarray(bb[d],dtype=int)-np.asarray(aa[d],dtype=int)
          for d in days}
    rng=np.random.default_rng(seed)
    all_deltas=np.concatenate([diff[d] for d in days])
    boots=[]
    for _ in range(repetitions):
        sample=rng.integers(0,len(days),size=len(days))
        x=np.concatenate([diff[days[int(i)]] for i in sample])
        boots.append(float(x.mean()))
    return {"n_dates":len(days),"n_races":len(all_deltas),
      "hit_rate_delta":float(all_deltas.mean()),
      "paired_date_bootstrap95":list(map(float,np.quantile(boots,[.025,.975])))}


def study(db,overlay,history_script,model_path,output_dir):
    model,hist,mean,scale,weights=validate_source(db,overlay,history_script,model_path)
    race_data,exclusions=hist.build_dataset(db=db,overlay=overlay)
    X,rank,race_ids,states,years,numbers,winner_nums=hist.create_feature_rows(race_data,"full")
    groups=groups_for(race_ids,rank,years,states,race_data)
    fit,search,confirm,split=make_splits(groups)
    std=(X-mean)/scale

    # Candidate family comparisons; ALL fitted on first 40% 2025 only.
    fit_records=record_scores(std,fit,weights)
    search_records=record_scores(std,search,weights)
    families={family:candidate(fit_records,family)
              for family in CALIBRATION_FAMILIES}
    cv={family:evaluate_group(search_records,cal)
        for family,cal in families.items()}
    chosen_family=choice_for_family(cv)
    cal=families[chosen_family]

    # Independent coefficient group search on the SAME 2025 search window.
    # Group choices are pre-specified and modest; choose no more than one group.
    base=evaluate_group(search_records,cal)
    candidate_metrics={"original":base}
    choices={"original":{"group":None,"factor":1.0}}
    for name in GROUPS:
        for factor in FACTORS:
            if factor==1.0:continue
            key=name+"__x"+str(factor)
            w=scale_stage1(weights,name,factor)
            r=record_scores(std,search,w)
            candidate_metrics[key]=evaluate_group(r,cal)
            choices[key]={"group":name,"factor":factor}
    selected=coefficient_choice(candidate_metrics,base)
    selected_w=scale_stage1(weights,**choices[selected])
    if selected=="original" and not np.array_equal(selected_w,weights):
        raise RuntimeError("original coefficient choice must be unchanged")

    # Truly later 2025 dates: never used to fit temperatures or choose factor.
    a=record_scores(std,confirm,weights)
    b=record_scores(std,confirm,selected_w)
    confirm_base=evaluate_group(a,cal)
    confirm_choice=evaluate_group(b,cal)
    certainty=bootstrap_paired_hits((a,cal),(b,cal))
    # Adoption gate decided before looking at 2026.
    accepted=(selected!="original" and
        certainty["paired_date_bootstrap95"][0]>0.0 and
        confirm_choice["winner_logloss"]<confirm_base["winner_logloss"] and
        confirm_choice["winner_brier"]<=confirm_base["winner_brier"]+.001 and
        confirm_choice["ece_confidence"]<=confirm_base["ece_confidence"]+.005)
    frozen=selected_w if accepted else weights
    realized_selected=selected if accepted else "original"

    # Re-fit only the CALIBRATION on all of 2025 after the acceptance
    # decision has been made. Do not retrain stage coefficients on 2026.
    entire=fit+search+confirm
    final_cal=candidate(record_scores(std,entire,frozen),chosen_family)
    year26=[g for g in groups
        if g["year"]==2026 and g["status"]=="validated_result"]
    audit_original=evaluate_group(record_scores(std,year26,weights),model["calibration"])
    audit_frozen=evaluate_group(record_scores(std,year26,frozen),final_cal)

    out={"schema":"jra-v51-2025-chronological-feature-and-calibration-ablation-v1",
      "model_v51_official_unchanged":True,"production_override":False,
      "source":{"db_sha256":file_sha(db),"overlay_sha256":file_sha(overlay),
         "original_model_sha256":file_sha(model_path),
         "history_script_sha256":file_sha(history_script)},
      "splits":split,"feature_groups":{k:list(v) for k,v in GROUPS.items()},
      "bodyweight":{"included_in_31_features":False,
        "result":"NOT_FIT_FROM_RETROSPECTIVE_RESULT_WEIGHTS",
        "reason":"2026 auxiliary weight study did not show top1 uplift; contemporaneous verified weight observation required"},
      "2025_calibration_search":cv,"selected_calibration_family":chosen_family,
      "2025_coefficient_search":candidate_metrics,
      "selected_candidate_search_only":selected,"2025_final_temporal_confirmation":{
        "baseline":confirm_base,"candidate":confirm_choice,
        "paired_winner_bootstrap":certainty,"predeclared_gate_passed":bool(accepted)},
      "applied_proposal":realized_selected,
      "fit_final_calibration_on_2025_only":final_cal,
      "audit_2026_frozen_no_selection":{"existing_official":audit_original,
        "candidate_or_unchanged":audit_frozen},
      "status":"RESEARCH_REPORT_NOT_AUTO_PROMOTED",
      "limits":["2025 final confirmation does not repair historical evidence publication-time uncertainty.",
                "2026 has already been inspected in older studies: only a fixed research audit.",
                "Coefficient scaling is sensitivity analysis, not a new independently trained model.",
                "No bodyweight factor is fitted without timestamp-authenticated preoff observations."]}
    proposal=copy.deepcopy(model)
    proposal["stage_coefficients"]=frozen.tolist()
    proposal["calibration"]=final_cal
    proposal["production_enabled"]=False
    proposal["standard_version"]="research_candidate_not_official"
    proposal["calibration_research_source_report"]="v51_2025_coefficient_calibration_grid.json"
    target=Path(output_dir)
    save_new(target/"v51_2025_coefficient_calibration_grid.json",out)
    save_new(target/"v51_2025_coefficient_calibration_research_model.json",proposal)
    return out


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--database",required=True)
    p.add_argument("--review-overlay",required=True)
    p.add_argument("--historical-feature-script",required=True)
    p.add_argument("--model",required=True)
    p.add_argument("--output-dir",required=True)
    a=p.parse_args()
    x=study(a.database,a.review_overlay,a.historical_feature_script,
            a.model,a.output_dir)
    print(json.dumps({"selected_family":x["selected_calibration_family"],
       "searched":x["selected_candidate_search_only"],
       "applied_research_only":x["applied_proposal"],
       "2025_temporal_confirmation":x["2025_final_temporal_confirmation"],
       "2026_audit":x["audit_2026_frozen_no_selection"],
       "production_changed":False},ensure_ascii=False))

if __name__=="__main__":
    main()
