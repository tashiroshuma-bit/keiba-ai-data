"""Experimental point-in-time body-weight overlay of saved v50 win probabilities.
Research only; never overwrites v50, never infers weight information at race start.
"""
import json
import math
from pathlib import Path

POLICY=Path(__file__).resolve().parents[1]/"operations/prediction_policy/v51_body_weight_shadow_research.json"

def apply(v50_horses, weight_rows, *, policy_path=POLICY, asof):
    """Return an independent v51 shadow field, preserving v50_horses."""
    policy=json.loads(Path(policy_path).read_text())
    if policy["version"]!="v51" or policy["production_enabled"] is not False:
        raise ValueError("V51 must remain non-production")
    if not isinstance(asof,str) or not asof:
        raise ValueError("explicit as-of required")
    if not v50_horses or len(v50_horses)!=len(weight_rows):
        raise ValueError("complete v50 and weight fields required")
    if len({str(x["number"]) for x in v50_horses})!=len(v50_horses):
        raise ValueError("duplicate v50 horse number")
    by_number={str(x["number"]):x for x in weight_rows}
    if set(by_number)!={str(x["number"]) for x in v50_horses}:
        raise ValueError("horse roster mismatch")
    base=[float(x["v50_p1"]) for x in v50_horses]
    if any(not math.isfinite(p) or p<=0 for p in base) or abs(sum(base)-1)>1e-5:
        raise ValueError("v50 p1 invalid")
    scores=[]
    for horse,p in zip(v50_horses,base):
        row=by_number[str(horse["number"])]
        if row.get("weight_observed_at") is None or row["weight_observed_at"]>asof:
            raise ValueError("no proven preoff weight observation")
        if row.get("asof")!=asof:
            raise ValueError("weight snapshot asof mismatch")
        group=row.get("weight_change_bucket")
        if group is None:
            raise ValueError("explicit missing bucket required")
        if group not in policy["bodyweight_factors"]:
            raise ValueError("unknown body-weight change category")
        scores.append(p*policy["bodyweight_factors"][group])
    norm=sum(scores)
    return {"status":"SHADOW_NOT_PRODUCTION_NOT_V50_VALIDATED",
            "asof":asof,"v50_unchanged":True,
            "horses":[{"number":h["number"],"v50_p1":p,"v51_shadow_p1":s/norm}
                      for h,p,s in zip(v50_horses,base,scores)]}
