"""Validate a saved V51 official prediction JSON without rerunning inference."""
import argparse
import datetime as dt
import json
import math
from pathlib import Path


def validate(path):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = []
    if doc.get("schema") != "jra-v51-official-forecast-v1" or doc.get("version") != "v51":
        errors.append("INVALID_OFFICIAL_SCHEMA")
    if doc.get("v50_used") is not False or doc.get("no_live_bets") is not True:
        errors.append("UNAUTHORIZED_MODEL_OR_BETS")
    try:
        asof = dt.datetime.fromisoformat(doc["forecast_asof"].replace("Z", "+00:00"))
        if asof.tzinfo is None:
            raise ValueError("naive asof")
    except (ValueError, KeyError, TypeError):
        errors.append("INVALID_ASOF")
        asof = None
    races = doc.get("races")
    if not isinstance(races, list) or not races:
        errors.append("EMPTY_RACES")
        races = []
    seen = set()
    for race in races:
        rid = race.get("race")
        if not rid or rid in seen:
            errors.append("DUPLICATE_OR_MISSING_RACE")
        seen.add(rid)
        try:
            off = dt.datetime.fromisoformat(race["race_off_at"].replace("Z", "+00:00"))
            if asof is not None and (off.tzinfo is None or off <= asof):
                errors.append(str(rid) + ":NOT_PREOFF")
        except (KeyError, TypeError, ValueError):
            errors.append(str(rid) + ":INVALID_OFF")
        horses = race.get("runners", [])
        if len(horses) < 3:
            errors.append(str(rid) + ":INSUFFICIENT_RUNNERS")
            continue
        nums = [h.get("number") for h in horses]
        if len(set(map(str, nums))) != len(nums):
            errors.append(str(rid) + ":DUPLICATE_RUNNERS")
        for key in ("p1", "p2", "p3"):
            vals = [h.get(key) for h in horses]
            if any(type(x) not in (float, int) or not math.isfinite(x) or x < 0 or x > 1 for x in vals):
                errors.append(str(rid) + ":" + key + "_INVALID")
            elif abs(sum(vals) - 1.0) > 1e-8:
                errors.append(str(rid) + ":" + key + "_NOT_NORMALIZED")
        for h in horses:
            if type(h.get("p_top3")) in (float, int) and all(type(h.get(k)) in (float, int) for k in ("p1", "p2", "p3")):
                if abs(h["p_top3"] - sum(h[k] for k in ("p1", "p2", "p3"))) > 1e-8:
                    errors.append(str(rid) + ":TOP3_MARGINAL_MISMATCH")
            else:
                errors.append(str(rid) + ":TOP3_MARGINAL_MISSING")
        audit = race.get("combination_audit", {})
        if type(audit.get("mass")) not in (int, float) or not math.isfinite(audit["mass"]) or abs(audit["mass"] - 1) > 1e-8:
            errors.append(str(rid) + ":JOINT_MASS_INVALID")
        if audit.get("ordered_total") != len(horses) * (len(horses)-1) * (len(horses)-2):
            errors.append(str(rid) + ":JOINT_COMBINATIONS_INCOMPLETE")
    return {"status": "VERIFIED" if not errors else "INVALID", "race_count": len(races), "issues": errors}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--forecast", required=True)
    args = p.parse_args()
    result = validate(args.forecast)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not result["issues"] else 2)
