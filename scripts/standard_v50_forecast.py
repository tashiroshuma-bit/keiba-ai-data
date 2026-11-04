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
    from scripts.build_v50_rider_residuals import build, file_sha256
    from scripts.run_v50_preoff import run, parse_time
except ModuleNotFoundError:
    from build_v50_rider_residuals import build, file_sha256
    from run_v50_preoff import run, parse_time

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_POLICY=ROOT/"operations/prediction_policy/standard_v50.json"

def standard_forecast(forecast_path, database_path, output_path, *,
                      state_path=ROOT/"PROJECT_STATE.json",policy_path=DEFAULT_POLICY):
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
    args=p.parse_args()
    result=standard_forecast(args.forecast,args.database,args.output)
    print(json.dumps({"version":result["version"],"races":len(result["races"]),
                      "standard_forecast":True,
                      "policy_sha256":result["policy_sha256"],
                      "live_bet_generation":False},ensure_ascii=False))

if __name__=="__main__":
    main()
