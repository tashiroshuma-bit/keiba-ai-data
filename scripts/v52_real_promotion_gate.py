"""V52 formal production-promotion guard for a GENUINELY fitted Joint Top3 model.

A successful synthetic unit test does not authorize a production release.
This module takes on-disk result files from the full 362MB canonical run;
if they do not exist, any activation fails before writing release files.

The user authorized aiming for V52 production; training success and
verified point-in-time preoff feature availability remain prerequisites.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np

DB_SHA="5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd"
OVERLAY_SHA="5f80b199b61b401fb046a0d7c2fb065b8c433dbc5734fcbefb5f0740ae3d03ea"
REPORT_SCHEMA="jra-v51-joint-pl-major-statistical-rebuild-20261114-v1"

def _safe_number(obj):
    return type(obj) in (float,int) and math.isfinite(obj)

def _validate_metrics(record,n):
    required=("races","top1_hits","top1_accuracy","winner_logloss",
              "winner_brier","ece_confidence",
              "conditional_second_logloss","conditional_third_logloss")
    if any(k not in record for k in required):
        raise ValueError("V52 missing independently compared metric")
    if record["races"]!=n or not 0<=record["top1_hits"]<=n:
        raise ValueError("V52 expected real cohort is absent")
    if not all(_safe_number(record[k]) for k in required[2:]):
        raise ValueError("V52 observed metric not finite")

def check_promotion_evidence(report,proposal,preoff_smoke):
    """Fail closed unless all sources, chronological scores, 71 coefficients,
    three stages, uncertainty gate, and preoff 45-feature materialization pass.
    """
    if report.get("schema")!=REPORT_SCHEMA:
        raise ValueError("V52 real source comparison schema missing")
    src=report.get("sources",{})
    if src.get("v12_sha256")!=DB_SHA or src.get("review_sha256")!=OVERLAY_SHA:
        raise ValueError("V52 canonical source verification absent")
    cohort=report.get("cohorts",{})
    splits=cohort.get("2025",{})
    if cohort.get("train_2023_2024")!=5865:
        raise ValueError("V52 historical 2023/2024 study not complete")
    if (splits.get("fit_races"),splits.get("search_races"),
        splits.get("confirm_races"),splits.get("all_2025_races")
        )!=(1145,1186,594,2925):
        raise ValueError("V52 heldout 2025 chronology inconsistent")
    if cohort.get("audit_2026")!=2411 or report.get("total_feature_count")!=71:
        raise ValueError("V52 full-race cohort or new design absent")
    name=report.get("chosen_on_middle_2025")
    if not name or name=="baseline":
        raise ValueError("V52 candidate not independently selected")
    if name not in report.get("candidate_optimizations",{}):
        raise ValueError("V52 chosen model lacks recorded optimizer")
    late=report.get("late_2025_confirmation",{})
    if late.get("promotion_gate_passed") is not True:
        raise ValueError("V52 chronological statistical acceptance failed")
    for key in ("baseline","candidate"):
        _validate_metrics(late.get(key,{}),594)
    audit=report.get("2026_postselection_audit",{})
    for key in ("legacy_baseline","joint_candidate"):
        _validate_metrics(audit.get(key,{}),2411)
    if audit["legacy_baseline"]["top1_hits"]!=603:
        raise ValueError("V52 baseline historical reproduction failed")
    for year,podium_key in ((late,"baseline_podium"),(late,"candidate_podium"),
                            (audit,"legacy_podium"),(audit,"joint_podium")):
        podium=year.get(podium_key,{})
        if podium.get("n_valid") is None or podium.get("n_valid")<=0:
            raise ValueError("V52 actual top-three labels absent")
        if not all(type(podium.get(k)) is int for k in
                   ("ordered_hits","unordered_hits")):
            raise ValueError("V52 top-three exact hits not evaluated")
    if (report.get("2026_used_to_select_hyperparameters") is not False
        or report.get("same_race_result_used_as_feature") is not False
        or report.get("minimum_prior_result_age_calendar_days")!=2):
        raise ValueError("V52 retrospective leakage restrictions failed")
    intervals=late.get("paired_day_bootstrap",{}).get(
        "paired_calendar_day_95ci",{})
    for key in ("top1_hit","winner_logloss","winner_brier",
                "ordered_hit","unordered_hit"):
        ci=intervals.get(key)
        if not isinstance(ci,list) or len(ci)!=2 or not all(
            _safe_number(x) for x in ci):
            raise ValueError("V52 heldout paired-day uncertainty absent")
    if proposal.get("schema")!=REPORT_SCHEMA:
        raise ValueError("V52 joint model candidate not fitted")
    if proposal.get("production_enabled") is not False:
        raise ValueError("V52 research proposal must not already be deployed")
    if proposal.get("source_db_sha256")!=DB_SHA:
        raise ValueError("V52 trained model source mismatch")
    if proposal.get("selected_hyperparameters",{}).get("config")!=(
        report["candidate_optimizations"][name]["config"]):
        raise ValueError("V52 fit candidate mismatches selected optimization")
    arr=np.asarray(proposal.get("coefficients_joint_top3"),dtype=float)
    if arr.shape!=(3,71) or not np.isfinite(arr).all():
        raise ValueError("V52 trained real 3x71 coefficients required")
    manifest=proposal.get("feature_manifest",{})
    if len(manifest.get("input_names",[]))!=45 or len(
        manifest.get("basis_names",[]))!=71:
        raise ValueError("V52 raw45-to-designed71 source features absent")
    if not isinstance(proposal.get("calibration"),dict) or not proposal["calibration"]:
        raise ValueError("V52 2025-fitted calibration absent")
    if (preoff_smoke.get("schema")!="jra-v52-real-preoff-smoke-v1"
        or preoff_smoke.get("canonical_db_sha256")!=DB_SHA
        or preoff_smoke.get("model_candidate")!=name
        or preoff_smoke.get("completed") is not True
        or preoff_smoke.get("all_45_features_observed_before_asof") is not True
        or preoff_smoke.get("verified_full_field") is not True
        or preoff_smoke.get("official_identity_evidence") is not True
        or preoff_smoke.get("published_at_before_forecast") is not True
        or not isinstance(preoff_smoke.get("source_sha256"),str)
        or len(preoff_smoke["source_sha256"])!=64):
        raise ValueError("V52 live as-of full-field feature evidence unverified")
    return {"source_sha256":DB_SHA,"selected":name,"trained_features":71,
            "compared_2025_late":594,"audit_2026":2411,
            "actual_vs_legacy_2025_top1":[late["baseline"]["top1_hits"],
                                         late["candidate"]["top1_hits"]],
            "production_evidence_verified":True}

def staged_to_production_model(proposal,evidence):
    """Generate a release payload only after actual canonical evidence."""
    out=copy.deepcopy(proposal)
    out["schema"]="jra-v52-official-joint-top3-pl-v1"
    out["standard_version"]="v52"
    out["model_family"]="hierarchical_regularized_top3_plackett_luce"
    out["production_enabled"]=True
    out["promotion_receipt"]=evidence
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--report",required=True)
    p.add_argument("--candidate",required=True)
    p.add_argument("--preoff-smoke",required=True)
    p.add_argument("--out-model",required=True)
    p.add_argument("--out-receipt",required=True)
    a=p.parse_args()
    model_out=Path(a.out_model)
    receipt_out=Path(a.out_receipt)
    if model_out.exists() or receipt_out.exists():
        raise FileExistsError("V52 release cannot overwrite previous artifacts")
    report=json.loads(Path(a.report).read_text(encoding="utf-8"))
    proposal=json.loads(Path(a.candidate).read_text(encoding="utf-8"))
    smoke=json.loads(Path(a.preoff_smoke).read_text(encoding="utf-8"))
    evidence=check_promotion_evidence(report,proposal,smoke)
    trained=staged_to_production_model(proposal,evidence)
    # Write only into a new output directory as a staged release.
    model_out.parent.mkdir(parents=True,exist_ok=True)
    receipt_out.parent.mkdir(parents=True,exist_ok=True)
    with model_out.open("x",encoding="utf-8") as f:
        json.dump(trained,f,ensure_ascii=False,indent=2)
        f.write("\n")
    with receipt_out.open("x",encoding="utf-8") as f:
        json.dump(evidence,f,ensure_ascii=False,indent=2)
        f.write("\n")
    print(json.dumps({"status":"V52_ACTUAL_TRAINED_RESEARCH_GATE_PASSED",
       "model_file":str(model_out),"receipt_file":str(receipt_out),
       "note":"Artifacts staged; PROJECT_STATE activation requires explicit validated release commit"}))
if __name__=="__main__":
    main()
