"""V51 second/third stage ridge search for exact podium ordering.

The user-approved V51 winner coefficients are fixed. Conditional second and
third stages are refitted on 2023-24 actual results. 2025 strictly date-split
fit/search/confirm; 2026 is a read-only retrospective audit. This never
changes official standard_v51_model.json or generates live wagers.
"""
from __future__ import annotations
import argparse
import copy
import json
import math
from pathlib import Path
import numpy as np
from scripts.v51_recovered_id_conditional_rank import (
    groups_for,stage_samples,fit_conditional_stage,calibrate,temp_fit,
    prepared_scores,stage_ce,make_race_probabilities,score_group,summarize,save_new
)
from scripts.v51_2025_coefficient_calibration_grid import (
    validate_source,make_splits,record_scores,file_sha
)

RIDGES=(0.003,0.01,0.03)

def candidates():
    out={"original":None}
    for t2 in RIDGES:
        for t3 in RIDGES:
            out[f"ridge2_{t2}_ridge3_{t3}"]=(t2,t3)
    return out

def fit_stages(std,train,original,ridge2,ridge3):
    w=original.copy()
    w[1],audit2=fit_conditional_stage(
        std,stage_samples(train,2),ridge=ridge2)
    w[2],audit3=fit_conditional_stage(
        std,stage_samples(train,3),ridge=ridge3)
    # NO p1 coefficient changes during ranking-stage experiment
    if not np.array_equal(w[0],original[0]):
        raise RuntimeError("p1 winner model unexpectedly changed")
    return w,{"second":audit2,"third":audit3}

def calibration_on_early_2025(std,fit,w,base_first):
    rec=record_scores(std,fit,w)
    c=copy.deepcopy(base_first)
    for stage in (2,3):
        c["global_stage_temperatures"][str(stage)]=temp_fit(rec,stage)[0]
    return c

def stage_score(records,cal):
    n=len(records)
    d={s:[] for s in (2,3)}
    for z,g in records:
        if not g["podium_valid"]:continue
        for s in (2,3):
            value=stage_ce(z,g,s,cal["global_stage_temperatures"][str(s)])
            if not math.isfinite(value):
                raise ValueError("invalid independent conditional rank log loss")
            d[s].append(value)
    if min(len(d[2]),len(d[3]))<200:raise ValueError("too few valid real podium races")
    return {"valid_podium_races":len(d[2]),
        "second_conditional_logloss":float(np.mean(d[2])),
        "third_conditional_logloss":float(np.mean(d[3])),
        "combined_conditional_logloss":float(np.mean(d[2])+np.mean(d[3]))}

def podium_result(records,cal,numbers):
    scored=[]
    for z,g in records:
        p=make_race_probabilities(z,cal)
        if abs(p["joint_normalization"]-1)>1e-8:
            raise ValueError("conditional podium distribution did not normalize")
        scored.append(score_group(z,g,p,numbers))
    summary=summarize(scored)
    return {
        "races":summary["n_races"],
        "unique_podium_races":summary["unique_podium_races"],
        "winner_hits":summary["top1_hits"],
        "top1_accuracy":summary["top1_accuracy"],
        "unordered_top3_exact":summary["unordered_podium_exact"],
        "ordered_top3_exact":summary["ordered_podium_exact"],
        "conditional_second_logloss":summary["mean_conditional_second_logloss"],
        "conditional_third_logloss":summary["mean_conditional_third_logloss"],
        "p2_marginal_logloss":summary["mean_second_marginal_logloss"],
        "p3_marginal_logloss":summary["mean_third_marginal_logloss"],
    }

def choose(scored):
    # No 2026 metrics or final 2025 dates are accepted by this selector.
    baseline=scored["original"]
    possible=[]
    for key,val in scored.items():
        if (val["second_conditional_logloss"] <= baseline["second_conditional_logloss"]+.003
            and val["third_conditional_logloss"] <= baseline["third_conditional_logloss"]+.003):
            possible.append((val["combined_conditional_logloss"],key))
    return min(possible)[1] if possible else "original"

def study(db,overlay,history_script,model_path,outdir):
    model,hist,mean,scale,original=validate_source(
        db,overlay,history_script,model_path)
    races,exclusions=hist.build_dataset(db=db,overlay=overlay)
    X,rank,rids,states,years,numbers,winner=hist.create_feature_rows(
        races,"full")
    allgroups=groups_for(rids,rank,years,states,races)
    train=[g for g in allgroups
        if g["year"]<=2024 and g["status"]=="validated_result"]
    fit,search,confirm,split=make_splits(allgroups)
    if len(train)!=5865:raise ValueError("different 2023-24 training race cohort")
    std=(X-mean)/scale
    # Fit the initial p1 calibration exclusively on early 2025, not entire 2025.
    early_winner_cal=calibrate(record_scores(std,fit,original))
    models={"original":original}
    optimizers={}
    for name,pair in candidates().items():
        if pair is None:continue
        models[name],optimizers[name]=fit_stages(std,train,original,*pair)
    calibrations={name:calibration_on_early_2025(std,fit,w,early_winner_cal)
        for name,w in models.items()}
    observed_search={name:stage_score(record_scores(std,search,w),calibrations[name])
        for name,w in models.items()}
    selected=choose(observed_search)
    # The later 2025 dates play no role in selecting the coefficient proposal.
    original_confirmation=podium_result(
        record_scores(std,confirm,original),calibrations["original"],numbers)
    candidate_confirmation=podium_result(
        record_scores(std,confirm,models[selected]),calibrations[selected],numbers)
    # Strict criterion for research endorsement: both podium exact metrics
    # and both conditional log losses must not degrade on later 2025.
    accept=(selected!="original"
        and candidate_confirmation["ordered_top3_exact"] > original_confirmation["ordered_top3_exact"]
        and candidate_confirmation["unordered_top3_exact"] >= original_confirmation["unordered_top3_exact"]
        and candidate_confirmation["conditional_second_logloss"] <= original_confirmation["conditional_second_logloss"]
        and candidate_confirmation["conditional_third_logloss"] <= original_confirmation["conditional_third_logloss"])
    endorsed=selected if accept else "original"
    frozen=models[endorsed]
    # After selection is sealed, refit temperatures on ALL 2025 observations.
    final_cal=calibrate(record_scores(std,fit+search+confirm,frozen))
    year26=[g for g in allgroups
        if g["year"]==2026 and g["status"]=="validated_result"]
    audit={
        "official_v51":podium_result(record_scores(std,year26,original),
                                   model["calibration"],numbers),
        "proposed_or_unchanged":podium_result(record_scores(std,year26,frozen),
                                           final_cal,numbers)}
    report={"schema":"jra-v51-p2p3-2025-chronological-ridge-ordered-podium-study-v1",
      "official_v51_unchanged":True,"auto_promoted":False,
      "source_v12_sha256":file_sha(db),"review_sidecar_sha256":file_sha(overlay),
      "model_input_sha256":file_sha(model_path),"train_2023_2024_races":len(train),
      "time_splits_2025":split,"candidate_ridges":list(RIDGES),
      "optimizer_audits":optimizers,
      "2025_search":observed_search,"selected_on_2025_middle_dates":selected,
      "2025_later_confirm":{"official":original_confirmation,
          "candidate":candidate_confirmation,"ordered_podium_gate_passed":bool(accept)},
      "endorsed_research_candidate":endorsed,
      "frozen_2026_audit_no_tuning":audit,
      "status":"RESEARCH_ONLY_PENDING_FULL_POINT_IN_TIME_EVIDENCE",
      "limitations":["Winner p1 weights are unchanged; top1 picks cannot improve in this study.",
         "2026 has been reviewed elsewhere; it is not a pristine prospective holdout.",
         "Historical PDF publication timestamps are incomplete; retrospective modeling differs from a truly frozen preoff forecast.",
         "Conditional-stage ridge choices alone cannot prove future ordered exact-three superiority."]}
    proposal=copy.deepcopy(model)
    proposal["stage_coefficients"]=frozen.tolist()
    proposal["calibration"]=final_cal
    proposal["production_enabled"]=False
    proposal["standard_version"]="v51_research_p2p3_not_approved"
    root=Path(outdir)
    save_new(root/"v51_2025_conditional_p2p3_ridge_report.json",report)
    save_new(root/"v51_2025_conditional_p2p3_research_model.json",proposal)
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
    print(json.dumps({"selected":result["selected_on_2025_middle_dates"],
      "endorsed":result["endorsed_research_candidate"],
      "confirmed":result["2025_later_confirm"]["ordered_podium_gate_passed"],
      "2026":result["frozen_2026_audit_no_tuning"],
      "production_changed":False},ensure_ascii=False))

if __name__=="__main__":main()
