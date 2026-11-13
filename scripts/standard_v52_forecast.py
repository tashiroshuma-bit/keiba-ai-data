"""Candidate V52 full-field preoff inference. Disabled until verified promotion.

Never substitute legacy V51 coefficients for the V52 joint-top3 fit.
Require trained 71-feature Joint PL weights, calibration, source lineage,
and race/runner-specific as-of provenance. Only the official project state
and policy activate this entrypoint.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from scripts.standard_v51_forecast import (
    digest,stamp,valid_sha,evidence_guard,combinations,
)
from scripts.v51_recovered_id_conditional_rank import make_race_probabilities
from scripts.v52_joint_pl_live_features import transform_live_features

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"PROJECT_STATE.json"
POLICY=ROOT/"operations/prediction_policy/standard_v52.json"
MODEL=ROOT/"operations/prediction_policy/standard_v52_model.json"
EXPECTED_DB="5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd"
GROUPS=("opponent_class","running_style","jockey_condition","previous_weight")

def validate_extra_provenance(h,asof,off):
    proof=h.get("v52_feature_evidence")
    if not isinstance(proof,dict) or set(proof)!=set(GROUPS):
        raise ValueError("V52 four-history-group provenance required")
    for name in GROUPS:
        item=proof[name]
        if not isinstance(item,dict):
            raise ValueError("invalid v52 history feature evidence")
        # A missing value is acceptable when accompanied by a documented
        # missing flag; it is not an inferred zero observation.
        if item.get("missing") is True:
            continue
        if item.get("missing") is not False:
            raise ValueError("V52 missingness not explicitly documented")
        url=str(item.get("source_url",""))
        if not url.startswith("https://www.jra.go.jp/"):
            raise ValueError("V52 observed prior feature must cite official JRA source")
        if not valid_sha(item.get("source_sha256")):
            raise ValueError("V52 observed prior feature requires source SHA")
        published=stamp(item["published_at"])
        observed=stamp(item["observed_at"])
        if not (published<=observed<=asof<off):
            raise ValueError("V52 post-asof feature evidence")
        # Historical result PDF content needs to be available well before
        # this forecast, not just same-day available as postrace output.
        if name in ("opponent_class","running_style","previous_weight"):
            if (off-published).total_seconds()<2*86400:
                raise ValueError("V52 historical feature requires 2-day embargo")

def forecast(snapshot_path,database_path,output_path,*,state_path=STATE,
             policy_path=POLICY,model_path=MODEL,top_combinations=20):
    output=Path(output_path)
    if output.exists():raise FileExistsError("V52 official prediction may not overwrite")
    state=json.loads(Path(state_path).read_text(encoding="utf-8"))
    current=state.get("standard_forecast",{})
    if (current.get("version")!="v52"
        or current.get("policy")!="operations/prediction_policy/standard_v52.json"
        or current.get("entrypoint")!="scripts/standard_v52_forecast.py"
        or current.get("model_path")!="operations/prediction_policy/standard_v52_model.json"
        or current.get("adopted_by_user") is not True):
        raise ValueError("V52 is NOT the official activated forecast")
    policy=json.loads(Path(policy_path).read_text(encoding="utf-8"))
    model=json.loads(Path(model_path).read_text(encoding="utf-8"))
    if (policy.get("standard_version")!="v52"
        or policy.get("standard_for_future_races") is not True
        or policy.get("v50_fallback") is not False
        or policy.get("v51_fallback") is not False
        or policy.get("model_path")!="operations/prediction_policy/standard_v52_model.json"
        or policy.get("live_bet_generation") is not False):
        raise ValueError("V52 official policy is not active or unauthorized fallback")
    if (model.get("standard_version")!="v52"
        or model.get("model_family")!="hierarchical_regularized_top3_plackett_luce"
        or model.get("production_enabled") is not True
        or model.get("source_db_sha256")!=EXPECTED_DB
        or policy.get("expected_canonical_db_sha256")!=EXPECTED_DB
        or state.get("database",{}).get("sha256")!=EXPECTED_DB
        or digest(database_path)!=EXPECTED_DB):
        raise ValueError("V52 verified real canonical DB and trained model required")
    w=np.asarray(model["coefficients_joint_top3"],dtype=np.float64)
    if w.shape!=(3,71) or not np.isfinite(w).all():
        raise ValueError("V52 lacks genuine finite 71-feature learned coefficients")
    manifest=model["feature_manifest"]
    calibration=model["calibration"]
    if not isinstance(calibration,dict) or not calibration:
        raise ValueError("V52 must be calibrated on verified 2025 data")
    doc=json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    if (doc.get("schema")!="jra-v52-preoff-feature-snapshot-v1"
        or doc.get("canonical_database_sha256")!=EXPECTED_DB
        or not isinstance(doc.get("races"),list) or not doc["races"]):
        raise ValueError("V52 official full-field snapshot missing")
    if not valid_sha(doc.get("roster_source_sha256")):
        raise ValueError("roster source SHA required")
    if not str(doc.get("roster_source_url","")).startswith("https://"):
        raise ValueError("full official roster URL required")
    asof=stamp(doc["forecast_asof"])
    if stamp(doc["roster_captured_at"])>asof:raise ValueError("post-asof roster")
    outputs=[];unique=set()
    for race in doc["races"]:
        rid=race["race"]
        if rid in unique:raise ValueError("duplicate race")
        unique.add(rid)
        off=stamp(race["race_off_at"])
        if not asof<off or stamp(race["features_generated_at"])>asof:
            raise ValueError("post-off or future-generated V52 features")
        horses=race["horses"]
        if not isinstance(horses,list) or len(horses)<3:
            raise ValueError("V52 incomplete field")
        nums=[h["number"] for h in horses]
        if any(type(n)!=int or n<1 for n in nums) or len(set(nums))!=len(nums):
            raise ValueError("invalid horse number")
        horses=sorted(horses,key=lambda r:r["number"])
        if len({h["horse_id"] for h in horses})!=len(horses):
            raise ValueError("duplicate horse identity")
        raw=[]
        for h in horses:
            evidence_guard(h,asof,off)
            validate_extra_provenance(h,asof,off)
            value=h.get("feature_values")
            if (not isinstance(value,list) or len(value)!=45
                or any(type(z) not in (int,float) or not math.isfinite(z)
                       for z in value)):
                raise ValueError("V52 45 preoff observed features required")
            raw.append(value)
        features=transform_live_features(raw,manifest)
        z=[features@w[k] for k in range(3)]
        probability=make_race_probabilities(z,calibration)
        combinations_top=combinations(z,[h["number"] for h in horses],
                                      calibration,top_combinations)
        if not all(abs(float(probability[k].sum())-1)<1e-8
                   for k in ("p1","p2","p3")):
            raise ValueError("V52 joint probabilities do not normalize")
        outputs.append({
            "race":rid,"race_off_at":race["race_off_at"],
            "runners":[{"number":h["number"],"name":h["name"],
                "horse_id":h["horse_id"],
                "p1":float(probability["p1"][i]),
                "p2":float(probability["p2"][i]),
                "p3":float(probability["p3"][i]),
                "p_top3":float(probability["top3_sum"][i])}
                for i,h in enumerate(horses)],
            "ordered_top3":[horses[i]["number"] for i in probability["ordered_pick"]],
            "unordered_top3":sorted(horses[i]["number"]
                                   for i in probability["unordered_pick"]),
            "ordered_top3_probability":float(probability["ordered_pick_probability"]),
            "unordered_top3_probability":float(probability["unordered_pick_probability"]),
            "combination_audit":combinations_top})
    result={
        "schema":"jra-v52-official-forecast-v1",
        "version":"v52","forecast_asof":doc["forecast_asof"],
        "input_sha256":digest(snapshot_path),"source_db_sha256":EXPECTED_DB,
        "model_sha256":digest(model_path),
        "races":outputs,"v50_used":False,"v51_fallback_used":False,
        "no_live_bets":True,
        "qualifier":"Results only valid for verified pre-off evidence and complete roster",
    }
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("x",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2);f.write("\n")
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--features",required=True)
    p.add_argument("--database",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--top-combinations",type=int,default=20)
    a=p.parse_args()
    result=forecast(a.features,a.database,a.output,
                    top_combinations=a.top_combinations)
    print(json.dumps({"version":result["version"],"races":len(result["races"]),
        "output":a.output,"no_fallback":True},ensure_ascii=False))
if __name__=="__main__":
    main()
