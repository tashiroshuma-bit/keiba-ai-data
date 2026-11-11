"""V51 *research-only* prior-history four-axis winner residual rank experiment.

The official 31-dimensional V51 scores stay frozen. New candidate features
are derived from history at least two calendar days old (annual JRA PDFs are
published on the next day, exact historical timestamp unknown). Current
bodyweight is NEVER obtained from race-result PDFs. A live announced weight
can enter only through v51_four_axis_preoff_research with JRA proof and time.

Chronology: 2023/24 train residual, 2025 first40% fit temperature,
2025 middle40% select, later20% confirmation, 2026 audit only.
"""
from __future__ import annotations
import argparse
import copy
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from scripts.v51_recovered_id_conditional_rank import (
    groups_for,calibrate,prepared_scores,save_new
)
from scripts.v51_calibration_refinement import metrics
from scripts.v51_2025_coefficient_calibration_grid import (
    validate_source,make_splits,bootstrap_paired_hits,file_sha
)
from scripts.v51_four_axis_historical_features import (
    FEATURE_NAMES,GROUPS,load_source_metadata,build_features,align_with_original
)

RIDGES=(.03,.10)
FEATURE_CANDIDATES={**{key:tuple(ix) for key,ix in GROUPS.items()},
                    "combined":tuple(range(len(FEATURE_NAMES)))}

def normalize_by_training(X,train_rows):
    x=np.asarray(X,dtype=np.float64)
    training=x[train_rows]
    means=training.mean(axis=0)
    scales=training.std(axis=0)
    scales=np.where(scales>1e-6,scales,1)
    z=(x-means)/scales
    if not np.isfinite(z).all():raise ValueError("invalid new features")
    return z,means,scales

def fit_residual(base_logits,extra,groups,ridge,maxiter=125):
    """Fit ONLY additive 1st-stage residual, not official V51 weights."""
    if not math.isfinite(ridge) or ridge<=0:
        raise ValueError("ridge must be positive")
    if not groups:raise ValueError("no prior real race training groups")
    indices=np.concatenate([g["indices"] for g in groups])
    winners=np.array([g["first"] for g in groups],dtype=int)
    lens=np.array([len(g["indices"]) for g in groups],dtype=int)
    offsets=np.r_[0,np.cumsum(lens)]
    old=np.asarray(base_logits,dtype=float)[indices]
    ex=np.asarray(extra,dtype=float)[indices]
    y=np.asarray(extra,dtype=float)[winners]
    yw=y.sum(axis=0)
    gold=np.asarray(base_logits,dtype=float)[winners]
    n=len(groups)
    if ex.shape[1]==0:raise ValueError("empty residual features")
    def objective(w):
        logits=old+ex@w
        mx=np.maximum.reduceat(logits,offsets[:-1])
        centered=np.exp(logits-np.repeat(mx,lens))
        sums=np.add.reduceat(centered,offsets[:-1])
        p=centered/np.repeat(sums,lens)
        nll=(sum(mx+np.log(sums))-sum(gold)-yw@w)/n+.5*ridge*(w@w)
        grad=(ex.T@p-yw)/n+ridge*w
        return float(nll),grad
    result=minimize(objective,np.zeros(ex.shape[1]),
                    jac=True,method="L-BFGS-B",
                    options={"maxiter":maxiter,"ftol":1e-9})
    if not result.success and float(result.jac@result.jac)>1e-7:
        raise RuntimeError("V51 residual fit did not converge: "+str(result.message))
    return np.asarray(result.x),{
        "train_races":n,"runners":len(indices),"ridge":ridge,
        "optimization_nll_penalized":float(result.fun),
        "optimizer_success":bool(result.success),
        "iterations":int(result.nit)}

def records(std,all_groups,weights,zextra,residual):
    out=[]
    for g in all_groups:
        z=prepared_scores(std,g,weights)
        z[0]=z[0]+zextra[g["indices"]]@residual
        out.append((z,g))
    return out

def candidates_for_training(raw_extra,training_indices):
    # Research data must contain actual past observations. Missing masks do
    # not by themselves authorize an ablation candidate.
    flags={
        "opponent_class":(2,3),
        "running_style":(7,),
        "jockey_condition":(10,),
        "previous_weight":(13,),
    }
    available={}
    observed_any=False
    for key,indices in FEATURE_CANDIDATES.items():
        if key=="combined":continue
        count=sum(np.count_nonzero(raw_extra[training_indices,flag]==0)
                  for flag in flags[key])
        if count<50:continue
        if all(np.std(raw_extra[training_indices,i])<1e-8 for i in indices):
            continue
        available[key]=tuple(indices)
        observed_any=True
    if observed_any:
        available["combined"]=FEATURE_CANDIDATES["combined"]
    return available

def select_candidate(search):
    base=search["official_baseline"]
    eligible=[]
    for key,s in search.items():
        if s["winner_logloss"]>base["winner_logloss"]+.02:
            continue
        if s["winner_brier"]>base["winner_brier"]+.01:
            continue
        if s["ece_confidence"]>base["ece_confidence"]+.025:
            continue
        eligible.append((-s["top1_accuracy"],s["winner_logloss"],key))
    return min(eligible)[2] if eligible else "official_baseline"

def study(database,overlay,history_script,model_path,output_dir):
    model,hist,mean,scale,weights=validate_source(
        database,overlay,history_script,model_path)
    races,skipped=hist.build_dataset(db=database,overlay=overlay)
    X,rank,rids,states,years,numbers,winners=hist.create_feature_rows(races,"full")
    gr=groups_for(rids,rank,years,states,races)
    training=[g for g in gr if g["year"]<=2024
              and g["status"]=="validated_result"]
    if len(training)!=5865:raise ValueError("training cohort changed")
    fit,search,confirm,split=make_splits(gr)
    raw,coverage=load_source_metadata(database,races)
    extras,real_coverage=build_features(races,raw,minimum_days=2)
    Xextra=align_with_original(extras,rids,numbers)
    orig=(X-mean)/scale
    trainrows=np.concatenate([g["indices"] for g in training])
    zextra,extra_mean,extra_scale=normalize_by_training(Xextra,trainrows)
    logits=orig@weights[0]
    all_candidates={"official_baseline":np.zeros(len(FEATURE_NAMES))}
    diagnostics={}
    for name,idx in candidates_for_training(Xextra,trainrows).items():
        for penalty in RIDGES:
            key=name+"_ridge_"+str(penalty)
            beta,detail=fit_residual(logits,zextra[:,idx],training,penalty)
            b=np.zeros(len(FEATURE_NAMES));b[list(idx)]=beta
            all_candidates[key]=b
            diagnostics[key]=detail
    if len(all_candidates)<2:
        raise ValueError("no independent historical features are present")

    # Each candidate gets early-2025 temperature calibration only.
    calibration={}
    search_metrics={}
    for name,beta in all_candidates.items():
        calibration[name]=calibrate(records(orig,fit,weights,zextra,beta))
        search_metrics[name]=metrics(records(orig,search,weights,zextra,beta),
                                     calibration[name])
    choice=select_candidate(search_metrics)
    original_late=records(orig,confirm,weights,zextra,all_candidates["official_baseline"])
    new_late=records(orig,confirm,weights,zextra,all_candidates[choice])
    before=metrics(original_late,calibration["official_baseline"])
    after=metrics(new_late,calibration[choice])
    bootstrap=bootstrap_paired_hits((original_late,calibration["official_baseline"]),
                                    (new_late,calibration[choice]))
    approved_research=(choice!="official_baseline"
       and bootstrap["paired_date_bootstrap95"][0]>0
       and after["winner_logloss"]<before["winner_logloss"]
       and after["winner_brier"]<=before["winner_brier"]+.001
       and after["ece_confidence"]<=before["ece_confidence"]+.005)
    final_name=choice if approved_research else "official_baseline"
    beta=all_candidates[final_name]
    # Fit calibration on all 2025 once candidate selection is sealed.
    fullcal=calibrate(records(orig,fit+search+confirm,weights,zextra,beta))
    year26=[g for g in gr if g["year"]==2026
            and g["status"]=="validated_result"]
    audit_old=metrics(records(orig,year26,weights,zextra,
                    all_candidates["official_baseline"]),model["calibration"])
    audit_new=metrics(records(orig,year26,weights,zextra,beta),fullcal)
    if audit_old["top1_hits"]!=603 or audit_old["races"]!=2411:
        raise ValueError("historical actual official V51 2026 not reproduced")
    report={
        "schema":"jra-v51-four-axis-residual-winner-2025-chronological-study-v1",
        "status":"RETROSPECTIVE_RESEARCH_ONLY_PRODUCTION_UNCHANGED",
        "source_db_sha256":file_sha(database),
        "overlay_sha256":file_sha(overlay),
        "source_original_model_sha256":file_sha(model_path),
        "history_availability":"previous_calendar_date>=2d assumption; historical publication timestamps missing",
        "official_feature_count":31,
        "new_feature_names":list(FEATURE_NAMES),
        "candidate_feature_groups":{k:list(v) for k,v in FEATURE_CANDIDATES.items()},
        "raw_canonical_source_coverage":coverage,
        "research_time_block_feature_coverage":real_coverage,
        "training_2023_2024_races":len(training),
        "2025_splits":split,
        "optimizers":diagnostics,
        "2025_search_metrics":search_metrics,
        "chosen_on_2025_search_only":choice,
        "2025_late_confirmation":{
            "original":before,"candidate":after,
            "paired_date_bootstrap":bootstrap,
            "strict_gate_pass":approved_research},
        "2026_frozen_audit_only":{
            "original_official_v51":audit_old,
            "research_candidate":audit_new},
        "active_v51_model_unmodified":True,
        "current_race_bodyweight_in_training":False,
        "current_bodyweight_preoff_verified_entries":0,
        "limitations":[
           "Only PAST reported bodyweight is included. Current race PDF bodyweight is forbidden.",
           "Actual published/observed timestamps for retrospective results are not supplied.",
           "Previously inspected 2026 results must not select coefficients.",
           "Only first-place residual is retrained; P2/P3 original stages are frozen."]
    }
    proposal={"schema":"jra-v51-additive-residual-four-axis-research-v1",
        "official_model_sha256":file_sha(model_path),
        "extra_feature_names":list(FEATURE_NAMES),
        "extra_feature_mean":extra_mean.tolist(),
        "extra_feature_scale":extra_scale.tolist(),
        "winner_residual_coefficients":beta.tolist(),
        "historical_pdf_minimum_age_days":2,
        "calibration":fullcal,
        "official_31_coefficients_unchanged":True,
        "production_enabled":False}
    root=Path(output_dir)
    save_new(root/"v51_four_axis_2025_rank_research_report.json",report)
    save_new(root/"v51_four_axis_2025_research_proposal.json",proposal)
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--database",required=True)
    p.add_argument("--review-overlay",required=True)
    p.add_argument("--historical-feature-script",required=True)
    p.add_argument("--model",required=True)
    p.add_argument("--output-dir",required=True)
    a=p.parse_args()
    result=study(a.database,a.review_overlay,a.historical_feature_script,
                 a.model,a.output_dir)
    print(json.dumps({"selected":result["chosen_on_2025_search_only"],
        "gate":result["2025_late_confirmation"]["strict_gate_pass"],
        "2026":result["2026_frozen_audit_only"],
        "live_changed":False},ensure_ascii=False))
if __name__=="__main__":
    main()
