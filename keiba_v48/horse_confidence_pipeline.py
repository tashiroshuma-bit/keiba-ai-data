"""Version-preserving candidate overlay for production pipeline integration.

A promotion gate must authorize applying the overlay; default remains baseline.
No existing saved forecasts are modified.
"""
import math

CANDIDATE_ID="horse_podium_confidence_20261101_frozen"
CANDIDATE_WEIGHT=.8
PRIOR_SCORE=.15
PRIOR_STARTS=8


def horse_adjustment(runner):
    n=int(runner.get("starts") or 0)
    w=int(runner.get("wins") or 0)
    s=int(runner.get("seconds") or 0)
    t=int(runner.get("thirds") or 0)
    if min(n,w,s,t)<0 or w+s+t>n:
        raise ValueError("invalid career totals")
    return CANDIDATE_WEIGHT*((w+.5*s+.25*t+PRIOR_SCORE*PRIOR_STARTS)/(n+PRIOR_STARTS)-PRIOR_SCORE)


def rank_horses(horses,runners,*,promoted=False):
    """Explicit opt-in only after promotion evidence and single-writer approval."""
    by_number={r["number"]:r for r in runners}
    def score(h):
        base=math.log(max(float(h["p1"]),1e-300))
        return base+(horse_adjustment(by_number[h["number"]]) if promoted else 0.)
    return sorted(horses,key=lambda h:(-score(h),int(h["number"])))


def candidate_probabilities(horses,runners,*,promoted=False):
    """Normalized p1 shadow distribution, with no p2/p3 recalibration claim."""
    if not promoted:
        return {h["number"]:h["p1"] for h in horses}
    by_number={r["number"]:r for r in runners}
    weights={h["number"]:float(h["p1"])*math.exp(horse_adjustment(by_number[h["number"]])) for h in horses}
    z=sum(weights.values())
    if z<=0 or not math.isfinite(z):
        raise ValueError("invalid normalization")
    return {number:value/z for number,value in weights.items()}
