"""Research-only V51 true winner-stage coefficient refit (2023-24 JRA).

Compares ridge strengths and feature-group exclusion models on dated 2025
splits, then audits fixed choice on 2026. P2/P3 stages stay unchanged.
No future race production coefficient or bodyweight updates.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import numpy as np

from scripts.v51_recovered_id_conditional_rank import (
    fit_conditional_stage, stage_samples, save_new
)
from scripts.v51_calibration_refinement import candidate
from scripts.v51_2025_coefficient_calibration_grid import (
    GROUPS,validate_source,record_scores,make_splits,evaluate_group,
    coefficient_choice,bootstrap_paired_hits,file_sha
)

EXPERIMENTS={
 "ridge_0.003":(.003,None),
 "ridge_0.01":(.01,None),
 "ridge_0.03":(.03,None),
 "drop_recent_form":(.01,"recent_form"),
 "drop_horse_course_distance":(.01,"horse_course_distance"),
 "drop_jockey_history":(.01,"jockey_history"),
 "drop_field_relative_strength":(.01,"field_relative_strength"),
}

def fit_one(std,train_groups,base,*,ridge=.01,drop=None,maxiter=150):
    if not 0<ridge<1:raise ValueError("ridge must be positive")
    if drop is not None and drop not in GROUPS:
        raise ValueError("unrecognized v51 ablation feature group")
    feature=std.copy()
    if drop:
        feature[:,list(GROUPS[drop])]=0.0
    coefficients,audit=fit_conditional_stage(
        feature,stage_samples(train_groups,1),ridge=ridge,maxiter=maxiter)
    trained=base.copy()
    trained[0]=coefficients
    if drop:
        trained[0,list(GROUPS[drop])]=0.0
    return trained,audit


def study(db,overlay,history_script,model_path,output_dir):
    model,hist,mean,scale,weights=validate_source(db,overlay,history_script,model_path)
    races,skipped=hist.build_dataset(db=db,overlay=overlay)
    X,rank,rids,states,years,numbers,winner=hist.create_feature_rows(races,"full")
    from scripts.v51_recovered_id_conditional_rank import groups_for
    groups=groups_for(rids,rank,years,states,races)
    train=sorted((g for g in groups if g["year"]<=2024
        and g["status"]=="validated_result"),key=lambda g:(g["date"],g["race"]))
    if len(train)!=5865:
        raise ValueError("unexpected frozen 2023-2024 learner cohort")
    fit,search,confirm,split=make_splits(groups)
    std=(X-mean)/scale
    saved={"original":weights}
    audits={}
    for key,(ridge,drop) in EXPERIMENTS.items():
        saved[key],audits[key]=fit_one(std,train,weights,ridge=ridge,drop=drop)

    # Every experiment fits its own temperature ONLY on early 2025.
    cal={}
    scores={}
    for name,coefs in saved.items():
        cal[name]=candidate(record_scores(std,fit,coefs),"half-shrunk-strata")
        scores[name]=evaluate_group(record_scores(std,search,coefs),cal[name])
    selected=coefficient_choice(scores,scores["original"])

    # Subsequent late 2025 scores cannot influence candidate selection.
    a=record_scores(std,confirm,weights)
    b=record_scores(std,confirm,saved[selected])
    before=evaluate_group(a,cal["original"])
    after=evaluate_group(b,cal[selected])
    ci=bootstrap_paired_hits((a,cal["original"]),(b,cal[selected]))
    accepted=(selected!="original" and
        ci["paired_date_bootstrap95"][0]>0 and
        after["winner_logloss"]<before["winner_logloss"] and
        after["winner_brier"]<=before["winner_brier"]+.001 and
        after["ece_confidence"]<=before["ece_confidence"]+.005)
    frozen=saved[selected] if accepted else weights
    final_name=selected if accepted else "original"
    final_cal=candidate(record_scores(std,fit+search+confirm,frozen),
                        "half-shrunk-strata")
    holdout=[g for g in groups if g["year"]==2026
        and g["status"]=="validated_result"]
    result={
      "schema":"jra-v51-2025-chronological-winner-stage-refit-research-v1",
      "production_mutated":False,"source_db_sha256":file_sha(db),
      "overlay_sha256":file_sha(overlay),"model_sha256":file_sha(model_path),
      "training_2023_2024_races":len(train),"split_2025":split,
      "experiments":{k:{"ridge":v[0],"excluded_group":v[1],
                        "optimizer_audit":audits[k]} for k,v in EXPERIMENTS.items()},
      "selected_using_2025_search_only":selected,
      "2025_search_metrics":scores,
      "2025_late_confirmation":{"existing":before,"candidate":after,
          "paired_dates_ci95":ci,"strict_gate":bool(accepted)},
      "retained_research_model":final_name,
      "2026_observation_only":{
         "original_existing_2025_calibrated":evaluate_group(record_scores(
            std,holdout,weights),model["calibration"]),
         "selected_frozen_2025_calibrated":evaluate_group(record_scores(
            std,holdout,frozen),final_cal)},
      "bodyweight":"NOT_INCLUDED_WITHOUT_PREOFF_TIMESTAMP",
      "status":"RESEARCH_STAGED_NOT_PRODUCTION",
      "limitations":["No certified historical publication time for full retrospective features",
           "2026 previously inspected; no hyperparameter selection based on 2026",
           "Only the winner stage is refit; P2/P3 remain official frozen coefficients"]}
    proposal=copy.deepcopy(model)
    proposal["stage_coefficients"]=frozen.tolist()
    proposal["calibration"]=final_cal
    proposal["production_enabled"]=False
    proposal["standard_version"]="v51_research_winner_refit"
    target=Path(output_dir)
    save_new(target/"v51_2025_winner_refit_report.json",result)
    save_new(target/"v51_2025_winner_refit_research_model.json",proposal)
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--database",required=True)
    p.add_argument("--review-overlay",required=True)
    p.add_argument("--historical-feature-script",required=True)
    p.add_argument("--model",required=True)
    p.add_argument("--output-dir",required=True)
    a=p.parse_args()
    outcome=study(a.database,a.review_overlay,a.historical_feature_script,
                  a.model,a.output_dir)
    print(json.dumps({"2025_selection":outcome["selected_using_2025_search_only"],
      "gate":outcome["2025_late_confirmation"]["strict_gate"],
      "2026_audit":outcome["2026_observation_only"],
      "official_model_changed":False},ensure_ascii=False))
if __name__=="__main__":
    main()
