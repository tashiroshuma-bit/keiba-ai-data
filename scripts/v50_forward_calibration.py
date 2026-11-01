"""Forward-only probability calibration audit for immutable paired forecasts.

Does not tune temperature or weight on evaluation data.
"""
import math
from scripts.v50_promotion_gate import assess


def audit(records, *, min_races=100):
    gate=assess(records,min_races=min_races)
    if len({r.get("preoff_frozen_sha256") for r in records}) != len(records):
        return {**gate,"promotion_eligible":False,"calibration":"not_evaluated","status":"duplicate_frozen_forecast_hash"}
    if not gate["promotion_eligible"]:
        return {**gate,"calibration":"not_evaluated"}
    out={"v49":{"logloss":0.0,"brier":0.0,"top1_hits":0},
         "v50":{"logloss":0.0,"brier":0.0,"top1_hits":0}}
    for r in records:
        truth=r["actual_winner_number"]
        for version in ("v49","v50"):
            values=r[version+"_p1"]
            if isinstance(values,list):
                probabilities={int(x["number"]):float(x["p1"]) for x in values}
            else:
                probabilities={int(k):float(v) for k,v in values.items()}
            if len(probabilities)<3 or truth not in probabilities:
                raise ValueError("missing or ambiguous winner in forecast")
            if abs(sum(probabilities.values())-1)>1e-5 or any(not math.isfinite(p) or p<=0 for p in probabilities.values()):
                raise ValueError("invalid probabilities")
            out[version]["logloss"]-=math.log(probabilities[truth])
            out[version]["brier"]+=sum((p-(n==truth))**2 for n,p in probabilities.items())
            out[version]["top1_hits"]+=int(max(probabilities,key=probabilities.get)==truth)
    n=len(records)
    for v in out.values():
        v["logloss"]/=n
        v["brier"]/=n
        v["top1_hit_rate"]=v["top1_hits"]/n
    # Conservative noninferiority: never promote a degraded ranking/calibration.
    acceptable=(out["v50"]["logloss"]<=out["v49"]["logloss"] and
                out["v50"]["brier"]<=out["v49"]["brier"] and
                out["v50"]["top1_hits"]>=out["v49"]["top1_hits"])
    return {**gate,"metrics":out,"calibration":"forward_audit_not_retrained",
            "promotion_eligible":acceptable,
            "status":"metrics_pass" if acceptable else "metrics_regressed"}
