"""Run genuine canonical JRA v12 modern joint top-3 statistical comparison.

2023/24 fit the simultaneous conditional winner/second/third PL likelihood.
2025 first 40% calibrate; middle 40% choose among preregistered variants;
late 20% is unseen confirmation. 2026 is after-selection audit only.

RESEARCH ONLY: never overwrite V51 production coefficients/forecast policy.
Requires canonical private Library DB bytes locally; GitHub CI runs tests
but must not claim it executed this actual 162k-row learner without DB.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np

from scripts.v51_joint_pl_new_statistics import (
    design_matrix,joint_stage_fit,race_score_records,
)
from scripts.v51_four_axis_historical_features import (
    FEATURE_NAMES,load_source_metadata,build_features,align_with_original
)
from scripts.v51_2025_coefficient_calibration_grid import (
    validate_source,make_splits,bootstrap_paired_hits
)
from scripts.v51_recovered_id_conditional_rank import (
    groups_for,calibrate,prepared_scores,make_race_probabilities,
)
from scripts.v51_calibration_refinement import metrics

RESEARCH_SCHEMA="jra-v51-joint-pl-major-statistical-rebuild-20261114-v1"
EXPECTED_DB="5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd"
EXPECTED_OVER="5f80b199b61b401fb046a0d7c2fb065b8c433dbc5734fcbefb5f0740ae3d03ea"
PRESET_GRID=(
  {"ridge":.025,"coupling":.05,"half_life_days":365},
  {"ridge":.05,"coupling":.05,"half_life_days":365},
  {"ridge":.05,"coupling":.15,"half_life_days":365},
  {"ridge":.10,"coupling":.15,"half_life_days":365},
  {"ridge":.05,"coupling":.15,"half_life_days":730},
  {"ridge":.10,"coupling":.30,"half_life_days":730},
  {"ridge":.05,"coupling":.15,"half_life_days":None},
)

def _fsha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):
            h.update(b)
    return h.hexdigest()

def _read_file_data(db,overlay,history,model):
    obj,hist,mean,scale,original_stage=validate_source(db,overlay,history,model)
    if _fsha(db)!=EXPECTED_DB or _fsha(overlay)!=EXPECTED_OVER:
        raise ValueError("authenticated canonical v12 source mismatch")
    races,skipped=hist.build_dataset(db=db,overlay=overlay)
    x,rank,rids,status,years,numbers,_=hist.create_feature_rows(races,"full")
    groups=groups_for(rids,rank,years,status,races)
    t=[g for g in groups if g["year"]<=2024 and g["status"]=="validated_result"]
    early,middle,late,split=make_splits(groups)
    if (len(t),len(early),len(middle),len(late))!=(5865,1145,1186,594):
        raise ValueError("canonical race-date folds unexpectedly changed")
    source,source_count=load_source_metadata(db,races)
    extra_dict,coverage=build_features(races,source,minimum_days=2)
    extra=align_with_original(extra_dict,rids,numbers)
    trainrows=np.concatenate([g["indices"] for g in t])
    full,normalizers=design_matrix(
        x,extra,hist.FEATURES,FEATURE_NAMES,trainrows)
    baseline=(x-np.asarray(mean))/np.asarray(scale)
    y26=[g for g in groups if g["year"]==2026
         and g["status"]=="validated_result"]
    if len(y26)!=2411:raise ValueError("year 2026 audit cohort changed")
    return obj,original_stage,baseline,full,normalizers,groups,t,early,middle,late,y26,split,source_count,coverage

def _records_original(x,groups,w):
    return [([x[g["indices"]]@w[i] for i in range(3)],g) for g in groups]

def _podium_score(pairs,cal):
    n=ordered=unordered=0
    out={}
    for z,g in pairs:
        if not g["podium_valid"]:continue
        res=make_race_probabilities(z,cal)
        loc={int(v):i for i,v in enumerate(g["indices"])}
        truth=(loc[int(g["first"])],loc[int(g["second"])],loc[int(g["third"])])
        oh=int(tuple(res["ordered_pick"])==truth)
        uh=int(set(res["unordered_pick"])==set(truth))
        n+=1;ordered+=oh;unordered+=uh
        out[g["race"]]={"race":g["race"],"date":g["date"],
                        "ordered_hit":oh,"unordered_hit":uh}
    return {"n_valid":n,"ordered_hits":ordered,"unordered_hits":unordered,
       "ordered_rate":ordered/n if n else None,
       "unordered_rate":unordered/n if n else None},out

def _winner_rows(pairs,cal):
    # Use same exact calibrator as official V51 metric implementation.
    from scripts.v51_recovered_id_conditional_rank import softmax,bucket
    res={}
    for z,g in pairs:
        raw=softmax(z[0])
        t=cal["winner_entropy_confidence_groups"][bucket(raw)]["temp"]
        p=softmax(z[0],t)
        true_local=int(np.where(g["indices"]==g["first"])[0][0])
        top=int(np.argmax(p))
        label=np.zeros(len(p));label[true_local]=1
        res[g["race"]]={"race":g["race"],"date":g["date"],
            "top1_hit":int(top==true_local),
            "winner_logloss":-float(np.log(max(p[true_local],1e-15))),
            "winner_brier":float(np.sum((p-label)**2)),
            "confidence":float(p[top])}
    return res

def paired_day_bootstrap(base,new,*,seed=20261114,repetitions=3000):
    """Paired day resampling: rank hit + proper scores and exact podium."""
    if set(base)!=set(new):raise ValueError("different heldout race lists")
    by_day={}
    keys=sorted(base)
    for race in keys:
        a,b=base[race],new[race]
        if a["date"]!=b["date"]:raise ValueError("misaligned race dates")
        by_day.setdefault(a["date"],[]).append(race)
    if len(by_day)<10:raise ValueError("too few heldout dates")
    dates=sorted(by_day)
    metrics_keys=("top1_hit","winner_logloss","winner_brier",
                  "ordered_hit","unordered_hit")
    rng=np.random.default_rng(seed)
    boot={key:[] for key in metrics_keys}
    for _ in range(repetitions):
        sampled=rng.integers(0,len(dates),size=len(dates))
        races=[race for pick in sampled for race in by_day[dates[int(pick)]]]
        for key in metrics_keys:
            eligible=[r for r in races if key in base[r] and key in new[r]]
            if eligible:
                delta=np.mean([new[r][key]-base[r][key] for r in eligible])
                boot[key].append(float(delta))
    return {"n_dates":len(dates),"n_races":len(keys),
        "paired_calendar_day_95ci":{
            key:[float(x) for x in np.quantile(vals,[.025,.975])]
            for key,vals in boot.items()},
        "point_deltas":{
            key:float(np.mean([new[r][key]-base[r][key]
               for r in keys if key in base[r] and key in new[r]]))
            for key in metrics_keys},
        "iterations":repetitions}

def combine_rows(winners,podium):
    return {race:{**item,**podium.get(race,{})} for race,item in winners.items()}

def _score_choice(scores,baseline):
    """Choose by a weighted PROPER log score over the entire podium.

    0.5 * P1 LogLoss + .3 * P2 conditional LogLoss
    + .2 * P3 conditional LogLoss; all available from fully verified
    podiums. This prevents choosing a winner-only candidate that
    systematically worsens second or third conditional probabilities.
    """
    needed=("winner_logloss","conditional_second_logloss",
            "conditional_third_logloss")
    if any(not math.isfinite(float(baseline[k])) for k in needed):
        raise ValueError("baseline podium conditional proper scores unavailable")
    feasible=[]
    for name,q in scores.items():
        if any(not math.isfinite(float(q[k])) for k in needed):
            continue
        if q["winner_logloss"]>baseline["winner_logloss"]+.01:continue
        if q["conditional_second_logloss"]>baseline["conditional_second_logloss"]+.03:continue
        if q["conditional_third_logloss"]>baseline["conditional_third_logloss"]+.03:continue
        if q["winner_brier"]>baseline["winner_brier"]+.01:continue
        if q["ece_confidence"]>baseline["ece_confidence"]+.02:continue
        joint=(.5*q["winner_logloss"]+
               .3*q["conditional_second_logloss"]+
               .2*q["conditional_third_logloss"])
        feasible.append((joint,q["winner_logloss"],-q["top1_accuracy"],name))
    return min(feasible)[-1] if feasible else "baseline"

def _first_stages(core,groups,modelw):
    return race_score_records(core,groups,modelw)

def study(db,overlay,history,model_path,outdir):
    (baseline_model,oldw,oldx,core,feature_manifest,groups,
     train,early,middle,late,year26,split,coverage,observed)=_read_file_data(
         db,overlay,history,model_path)
    # Freeze legacy 31-weight model and calibrate both models on identical
    # early 2025 races for a fair 2025 retrospective comparison.
    oldcal=calibrate(_records_original(oldx,early,oldw))
    original_mid=_records_original(oldx,middle,oldw)
    original_late=_records_original(oldx,late,oldw)
    original26=_records_original(oldx,year26,oldw)
    midbase=metrics(original_mid,oldcal)

    proposals={}
    candidates={}
    measured={"baseline":midbase}
    calibrations={"baseline":oldcal}
    for cfg in PRESET_GRID:
        key=("joint_pl_r"+str(cfg["ridge"])+"_couple"+str(cfg["coupling"])
             +"_half"+str(cfg["half_life_days"]))
        w,diag=joint_stage_fit(core,train,**cfg)
        cal=calibrate(_first_stages(core,early,w))
        measures=metrics(_first_stages(core,middle,w),cal)
        proposals[key]=w
        candidates[key]={"fit":diag,"config":cfg}
        calibrations[key]=cal
        measured[key]=measures
    choice=_score_choice(measured,midbase)
    selected=proposals.get(choice)
    late_new=(original_late if choice=="baseline"
              else _first_stages(core,late,selected))
    cal_new=calibrations[choice]
    latebase=metrics(original_late,oldcal)
    latemodel=metrics(late_new,cal_new)
    podium0,racepod0=_podium_score(original_late,oldcal)
    podium1,racepod1=_podium_score(late_new,cal_new)
    row0=combine_rows(_winner_rows(original_late,oldcal),racepod0)
    row1=combine_rows(_winner_rows(late_new,cal_new),racepod1)
    boot=paired_day_bootstrap(row0,row1)
    confidence=boot["paired_calendar_day_95ci"]
    # Guardrails: statistically confirmed winner-score AND podium accuracy.
    # Nonsignificant apparent lift must not be deployed.
    accepted=(choice!="baseline"
        and confidence["top1_hit"][0]>0
        and confidence["winner_logloss"][1]<0
        and confidence["winner_brier"][1]<=0
        and confidence["unordered_hit"][0]>=0
        and confidence["ordered_hit"][0]>=0)
    # 2026 is a frozen *post-selection* audit. Training/selection never uses it.
    audit_orig=metrics(original26,baseline_model["calibration"])
    audit_new=metrics(_first_stages(core,year26,selected),cal_new) if selected is not None else audit_orig
    p26orig,_=_podium_score(original26,baseline_model["calibration"])
    p26new,_=_podium_score(_first_stages(core,year26,selected),cal_new) if selected is not None else (p26orig,{})
    if (audit_orig["races"],audit_orig["top1_hits"])!=(2411,603):
        raise ValueError("official 2026 V51 baseline did not reproduce")
    report={
        "schema":RESEARCH_SCHEMA,"status":"RESEARCH_NOT_PRODUCTION",
        "sources":{"v12_sha256":_fsha(db),"review_sha256":_fsha(overlay),
            "model_sha256":_fsha(model_path)},
        "model":"shared_hierarchical_joint_top3_plackett_luce",
        "new_statistical_changes":[
            "Joint likelihood for first, second and third finishing stages",
            "Hierarchical pooling of stage coefficients to limit variance",
            "Piecewise-linear nonlinear priors and cross-feature interactions",
            "Training-only feature normalization and 2023/24 time decay",
            "2025 date-blocked calibration, selection and independent confirmation",
            "Proper LogLoss/Brier/ECE with paired-day bootstrap for 1st and podium",
            "2026 audit never used for selection"],
        "cohorts":{"train_2023_2024":len(train),"2025":split,
                   "audit_2026":len(year26)},
        "extra_feature_count":14,
        "total_feature_count":core.shape[1],
        "canonical_source_field_coverage":coverage,
        "observed_prior_feature_coverage":observed,
        "search_2025_middle_metrics":measured,
        "chosen_on_middle_2025":choice,
        "candidate_optimizations":candidates,
        "late_2025_confirmation":{
            "baseline":latebase,"candidate":latemodel,
            "baseline_podium":podium0,"candidate_podium":podium1,
            "paired_day_bootstrap":boot,"promotion_gate_passed":accepted},
        "2026_postselection_audit":{
            "legacy_baseline":audit_orig,"joint_candidate":audit_new,
            "legacy_podium":p26orig,"joint_podium":p26new},
        "production_enabled":False,
        "source_historical_pdf_published_at_known":False,
        "minimum_prior_result_age_calendar_days":2,
        "same_race_result_used_as_feature":False,
        "2026_used_to_select_hyperparameters":False,
        "notes":["2025 late is selection-independent but source is retrospective.",
           "Current-race bodyweight is never inferred from result PDFs.",
           "Top3 exact rankings require unambiguous first, second and third.",
           "No claim of real-data uplift unless model is actually executed."]}
    result_dir=Path(outdir)
    result_dir.mkdir(parents=True,exist_ok=False)
    model_record={
        "schema":RESEARCH_SCHEMA,"feature_manifest":feature_manifest,
        "selected_hyperparameters":candidates.get(choice),
        "coefficients_joint_top3":selected.tolist() if selected is not None else None,
        "calibration":cal_new,
        "production_enabled":False,
        "official_v51_model_unchanged":True,
        "source_db_sha256":_fsha(db)}
    (result_dir/"v51_joint_pl_real_statistical_comparison.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (result_dir/"v51_joint_pl_research_candidate.json").write_text(
        json.dumps(model_record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report

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
    print(json.dumps({
        "status":x["status"],
        "selected":x["chosen_on_middle_2025"],
        "late_2025":x["late_2025_confirmation"],
        "audit_2026":x["2026_postselection_audit"],
        "production_enabled":False},ensure_ascii=False))
if __name__=="__main__":
    main()
