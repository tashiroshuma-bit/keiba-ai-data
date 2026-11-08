"""Standard future v50 JRA forecast entrypoint.

The base A forecast must be generated from real pre-off information by the
existing source pipeline. Rebuild rider residuals from the canonical DB at
the input's as-of, then apply selected v50 temperature, preserving the input.
Official standard designation is a user policy, not a claim of superior
statistical predictive performance or permission to generate live bets.
"""
import argparse
import hashlib
import json
import tempfile
from pathlib import Path

try:
    from scripts.v50_preoff_odds_blend import combine as combine_market
except ModuleNotFoundError:
    from v50_preoff_odds_blend import combine as combine_market

try:
    from scripts.v50_conditional_rare_upset import from_files as rare_upset_shadow
except ModuleNotFoundError:
    from v50_conditional_rare_upset import from_files as rare_upset_shadow

try:
    from scripts.build_v50_rider_residuals import build, file_sha256
    from scripts.run_v50_preoff import run, parse_time
except ModuleNotFoundError:
    from build_v50_rider_residuals import build, file_sha256
    from run_v50_preoff import run, parse_time

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_POLICY=ROOT/"operations/prediction_policy/standard_v50.json"

def standard_forecast(forecast_path, database_path, output_path, *,
                      state_path=ROOT/"PROJECT_STATE.json",policy_path=DEFAULT_POLICY,
                      odds_path=None,odds_alpha=0.20):
    forecast_path=Path(forecast_path)
    database_path=Path(database_path)
    output_path=Path(output_path)
    if output_path.exists():
        raise FileExistsError("standard v50 output cannot be overwritten")
    policy_bytes=Path(policy_path).read_bytes()
    policy=json.loads(policy_bytes)
    state=json.loads(Path(state_path).read_text())
    if policy.get("standard_version")!="v50" or policy.get("standard_for_future_races") is not True:
        raise ValueError("standard v50 policy not activated")
    if policy.get("live_bet_generation") is not False:
        raise ValueError("live betting must remain disabled")
    standard=state.get("standard_forecast",{})
    if (standard.get("version")!="v50" or
        standard.get("policy")!="operations/prediction_policy/standard_v50.json" or
        standard.get("entrypoint")!="scripts/standard_v50_forecast.py" or
        standard.get("adopted_by_user") is not True):
        raise ValueError("PROJECT_STATE standard forecast routing mismatch")
    if (policy.get("forecast_entrypoint")!=standard["entrypoint"] or
        policy.get("history_lag_days")!=2 or
        policy.get("overlay_weight")!=1 or
        policy.get("probability_temperature")!=0.7):
        raise ValueError("standard v50 policy differs from approved parameters")
    if state["database"]["version"] != 10:
        raise ValueError("unexpected canonical database version")
    dbdigest=file_sha256(database_path)
    if dbdigest != state["database"]["sha256"]:
        raise ValueError("canonical database SHA256 mismatch; repository stub is not canonical")
    inp=json.loads(forecast_path.read_bytes())
    if inp.get("source_model")!="A":
        raise ValueError("source must explicitly identify internal A model")
    asof=parse_time(inp["asof"])
    if not inp.get("races"):
        raise ValueError("no forecast races")
    for race in inp["races"]:
        off=race.get("original_off_at")
        if not off or parse_time(off) <= asof:
            raise ValueError("no proven pre-off source timestamp for "+race.get("race","unknown"))
    snapshot=build(database_path,inp["asof"],history_lag_days=policy["history_lag_days"])
    if snapshot["database_sha256"] != dbdigest:
        raise ValueError("rider snapshot database mismatch")
    with tempfile.TemporaryDirectory() as work:
        rider_path=Path(work)/"riders.json"
        rider_path.write_text(json.dumps(snapshot,ensure_ascii=False),encoding="utf-8")
        prediction=run(forecast_path,rider_path,
                       weight=policy["overlay_weight"],
                       temperature=policy["probability_temperature"])
    # Optional odds research overlay: freeze strictly pre-off snapshots.
    # Existing canonical v50 race ranks remain unchanged unless separately
    # re-validated and approved for promotion. Never accept final odds.
    if odds_path is not None:
        odds_file=Path(odds_path)
        odds_bytes=odds_file.read_bytes()
        odds=json.loads(odds_bytes)
        snapshots=odds.get("races")
        if not isinstance(snapshots,list) or len(snapshots)!=len(prediction["races"]):
            raise ValueError("complete preoff odds snapshots required for all forecast races")
        by_key={x["race"]:x for x in snapshots}
        if len(by_key)!=len(snapshots):
            raise ValueError("duplicate race odds snapshot")
        source_races={x["race"]:x for x in inp["races"]}
        if set(by_key)!=set(source_races):
            raise ValueError("odds and base model race set mismatch")
        overlays=[]
        for r in prediction["races"]:
            key=r["race"]
            snapshot=by_key[key]
            if parse_time(snapshot["observed_at"])>asof:
                raise ValueError("odds capture newer than model asof; regenerate forecast asof")
            output=combine_market(r["v50"],snapshot,alpha=odds_alpha,
                                  off_at=source_races[key]["original_off_at"])
            overlays.append({"race":key,**output})
        prediction["odds_research_overlay"]={
            "status":"RESEARCH_NOT_CALIBRATED_NO_PRODUCTION_PROMOTION",
            "alpha":odds_alpha,
            "odds_source_sha256":hashlib.sha256(odds_bytes).hexdigest(),
            "races":overlays,
            "warnings":["Pre-off-only odds; research shadow ranking, no live betting",
                        "Canonical v50 rank and ticket allocations remain unchanged",
                        "Alpha=0.20 is a provisional experimental setting, not a trained optimum"]}
    # Rare-upset branch only evaluates pre-off uncertainty as a research
    # shadow. The rule did NOT pass the 2025 independent holdout; no automatic
    # extreme-upset probability multiplier or horse ranking change is allowed.
    rare_policy=ROOT/"operations/prediction_policy/v50_rare_upset_gate_research.json"
    extended=ROOT/"reports/v50_extended_upset_gate_2025.json"
    if rare_policy.exists():
        assessments=[]
        for row in prediction["races"]:
            assessments.append({"race":row["race"],
                **rare_upset_shadow(row["v50"],rare_policy,
                                    extended if extended.exists() else None)})
        prediction["conditional_rare_upset_research"]={
            "status":"SHADOW_NO_PRODUCTION_REWEIGHTING",
            "assessments":assessments,
            "updated_probabilities":False,
            "rule_proven_for_canonical_v50":False}
    prediction["standard_forecast"]=True
    prediction["policy_sha256"]=hashlib.sha256(policy_bytes).hexdigest()
    prediction["canonical_database_sha256"]=dbdigest
    prediction["model_entrypoint"]="scripts/standard_v50_forecast.py"
    prediction["calibration_temperature"]=policy["probability_temperature"]
    prediction["calibration_status"]="2026-10-31-selected; 2026-11-01 independent-day evaluation did not improve"
    prediction["live_bet_generation"]=False
    prediction["warnings"]=["v50 standard user-directed; historical predictive superiority not established",
                            "Source A probabilities must be from genuine contemporaneous pre-off capture"]
    output_path.parent.mkdir(parents=True,exist_ok=True)
    with output_path.open("x",encoding="utf-8") as file:
        json.dump(prediction,file,ensure_ascii=False,indent=2)
        file.write("\n")
    return prediction

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--forecast",required=True)
    p.add_argument("--database",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--odds-snapshot")
    p.add_argument("--odds-alpha",type=float,default=0.20)
    args=p.parse_args()
    result=standard_forecast(args.forecast,args.database,args.output,
                             odds_path=args.odds_snapshot,odds_alpha=args.odds_alpha)
    print(json.dumps({"version":result["version"],"races":len(result["races"]),
                      "standard_forecast":True,
                      "policy_sha256":result["policy_sha256"],
                      "live_bet_generation":False,
                      "odds_overlay_races":len(result.get("odds_research_overlay",{}).get("races",[]))},ensure_ascii=False))

if __name__=="__main__":
    main()
