"""Bridge saved A-D race probabilities into v50 without re-estimating A.

Research adapter only: canonical production entrypoint remains standard_v50_forecast.py.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

try:
    from scripts.v50_rider_overlay import forecast_v50
except ModuleNotFoundError:
    from v50_rider_overlay import forecast_v50


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("missing timestamp")
    value = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("timezone-aware timestamp required")
    return value


def bridge(saved, riders, *, temperature=0.7, weight=1.0,
           allow_historical=False, source_sha256=None, rider_sha256=None):
    """Requires contemporaneously saved A all-runner p1 and named rider snapshot."""
    races = saved.get("races")
    if not isinstance(races, list) or not races:
        raise ValueError("saved A-D races required")
    if riders.get("source") != "preoff_horse_ability_adjusted":
        raise ValueError("unverified rider source")
    if not isinstance(riders.get("residuals"), dict):
        raise ValueError("rider residuals required")
    observed = timestamp(saved.get("created_at") or saved.get("asof"))
    rider_asof = timestamp(riders["asof"])
    if rider_asof > observed:
        raise ValueError("future rider snapshot")
    if not (math.isfinite(temperature) and temperature > 0 and
            math.isfinite(weight)):
        raise ValueError("invalid v50 parameters")
    output, skipped, seen = [], [], set()
    for race in races:
        label = race.get("race")
        if not isinstance(label, str) or not label or label in seen:
            raise ValueError("missing or duplicate race identifier")
        seen.add(label)
        surface = race.get("surface")
        if surface == "jump":
            skipped.append({"race": label, "reason": "unsupported_jump_race"})
            continue
        if surface not in ("turf", "dirt"):
            raise ValueError(label + ": unsupported surface")
        off = timestamp(race.get("original_off_at") or race.get("off_at"))
        if not allow_historical and observed >= off:
            raise ValueError(label + ": source observed after race start")
        original = race.get("models", {}).get("A", {}).get("horses")
        runners = race.get("runners")
        if not isinstance(original, list) or len(original) < 3 or not isinstance(runners, list):
            raise ValueError(label + ": full A model and roster required")
        active = [h for h in runners if not h.get("withdrawn")]
        roster = {h["number"]: h for h in active}
        if (len(roster) != len(active) or len(original) != len(active)
                or len({h["number"] for h in original}) != len(original)
                or set(roster) != {h["number"] for h in original}):
            raise ValueError(label + ": runner number mismatch")
        horses = []
        for h in original:
            runner = roster[h["number"]]
            if runner.get("name") != h.get("name"):
                raise ValueError(label + ": runner name mismatch")
            horses.append({"number": h["number"], "name": h["name"],
                           "jockey_id": runner.get("jockey_id"), "p1": h["p1"]})
        scoped = {h["jockey_id"]: riders["residuals"][surface + ":" + h["jockey_id"]]
                  for h in horses if h.get("jockey_id")
                  and surface + ":" + h["jockey_id"] in riders["residuals"]}
        prediction = forecast_v50(horses, scoped, weight=weight, temperature=temperature)
        baseline = {h["number"]: h["p1"] for h in horses}
        prediction["v50"]["horses"] = [
            {**h, "A_p1": baseline[h["number"]]} for h in prediction["v50"]["horses"]
        ]
        output.append({"race": label, "date": race.get("date"),
                       "track": race.get("track"), "race_number": race.get("race_number"),
                       "surface": surface, "off_at": off.isoformat(),
                       "models_available": [m for m in ("A", "B", "C", "D") if m in race.get("models", {})],
                       **prediction})
    ranking = sorted([
        {"race": r["race"], "date": r.get("date"),
         "number": r["v50"]["horses"][0]["number"],
         "name": r["v50"]["horses"][0]["name"],
         "p1": r["v50"]["horses"][0]["p1"]}
        for r in output], key=lambda r: (-r["p1"], r["race"]))
    return {"schema": "v50-from-abcd-v1", "version": "v50",
            "standard_forecast": False,
            "probability_status": "research_saved_A_with_rider_snapshot",
            "source_created_at": observed.isoformat(), "rider_asof": rider_asof.isoformat(),
            "source_sha256": source_sha256, "rider_sha256": rider_sha256,
            "temperature": temperature, "weight": weight,
            "races_count": len(output), "skipped": skipped, "races": output,
            "ranked_by_top1_probability": ranking,
            "top5_by_date": {day: [r for r in ranking if r["date"] == day][:5]
                             for day in sorted({r["date"] for r in ranking if r["date"]})},
            "limitations": ["Not canonical production v50; requires independently verified saved A.",
                            "Rider snapshot may omit more recent historical results.",
                            "Only A is transformed; B-D are not recalibrated."]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--saved-abcd", required=True)
    parser.add_argument("--riders", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--weight", type=float, default=1.0)
    parser.add_argument("--allow-historical", action="store_true")
    args = parser.parse_args()
    target = Path(args.output)
    if target.exists():
        raise FileExistsError("prediction cannot be overwritten")
    source = Path(args.saved_abcd).read_bytes()
    rider_bytes = Path(args.riders).read_bytes()
    result = bridge(json.loads(source), json.loads(rider_bytes),
                    temperature=args.temperature, weight=args.weight,
                    allow_historical=args.allow_historical,
                    source_sha256=hashlib.sha256(source).hexdigest(),
                    rider_sha256=hashlib.sha256(rider_bytes).hexdigest())
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"races": result["races_count"],
                      "top5_by_date": result["top5_by_date"],
                      "skipped": result["skipped"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
