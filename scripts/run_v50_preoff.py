#!/usr/bin/env python3
"""Run v50 on a saved preoff forecast with an as-of rider residual snapshot.

Input forecast: {"asof":"ISO8601","races":[{"race":"...","horses":[
{"number":1,"name":"...","jockey_id":"jra:...","p1":0.2}, ...]}]}
Input rider snapshot: {"asof":"ISO8601","residuals":{"jra:...":0.03}}
Fail closed if the snapshot is newer than the forecast or race data invalid.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
try:
    from scripts.v50_rider_overlay import forecast_v50
except ModuleNotFoundError:
    from v50_rider_overlay import forecast_v50

def parse_time(value):
    timestamp=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return timestamp

def run(forecast_path, rider_path):
    forecast_bytes=Path(forecast_path).read_bytes()
    rider_bytes=Path(rider_path).read_bytes()
    forecast=json.loads(forecast_bytes)
    riders=json.loads(rider_bytes)
    forecast_time=parse_time(forecast["asof"])
    rider_time=parse_time(riders["asof"])
    if rider_time > forecast_time:
        raise ValueError("rider snapshot observed after forecast; future leakage")
    if riders.get("source") != "preoff_horse_ability_adjusted":
        raise ValueError("unverified rider residual source")
    residuals=riders["residuals"]
    if not isinstance(residuals,dict):
        raise ValueError("rider residuals must be a dictionary")
    races=forecast["races"]
    if not races:
        raise ValueError("no forecast races")
    output=[]
    for race in races:
        horses=race["horses"]
        if len(horses)<3:
            raise ValueError("minimum 3 runners")
        output.append({"race":race["race"],**forecast_v50(horses,residuals)})
    return {"version":"v50","updated":"2026-11-01",
            "forecast_asof":forecast["asof"],"rider_asof":riders["asof"],
            "forecast_sha256":hashlib.sha256(forecast_bytes).hexdigest(),
            "rider_sha256":hashlib.sha256(rider_bytes).hexdigest(),
            "races":output}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--forecast",required=True)
    p.add_argument("--riders",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    result=run(a.forecast,a.riders)
    path=Path(a.output)
    if path.exists():
        raise FileExistsError("frozen prediction cannot be overwritten")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")

if __name__=="__main__":
    main()
