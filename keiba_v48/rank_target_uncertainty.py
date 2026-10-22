"""Statistical uncertainty for all-race exact-rank hit rates.

This is a reporting guardrail, not a learner or a model promotion decision.
"""
import argparse
import json
import math
from statistics import NormalDist


TARGETS = {"winner_hit": 0.8, "ordered_all_hit": 0.5, "top3_all_hit": 0.6}


def wilson(hits, races, confidence=0.95):
    if type(hits) is not int or type(races) is not int or races < 1 or not 0 <= hits <= races:
        raise ValueError("valid integer hits and races required")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between zero and one")
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    p = hits / races
    denom = 1 + z*z/races
    center = (p + z*z/(2*races))/denom
    half = z * math.sqrt(p*(1-p)/races + z*z/(4*races*races))/denom
    return [max(0, center-half), min(1, center+half)]


def evaluate(counts, races, targets=TARGETS):
    if set(counts) != set(targets):
        raise ValueError("all three metrics must be supplied")
    out = {}
    for key, target in targets.items():
        if not isinstance(target, (int, float)) or not 0 < target <= 1:
            raise ValueError("invalid target")
        hits = counts[key]
        low, high = wilson(hits, races)
        out[key] = {"hits": hits, "races": races, "rate": hits/races,
                    "wilson_95": [low, high], "target": target,
                    "point_target_met": hits/races >= target,
                    "lower_bound_target_met": low >= target}
    return {"metrics": out,
            "all_point_targets_met": all(v["point_target_met"] for v in out.values()),
            "all_lower_bound_targets_met": all(v["lower_bound_target_met"] for v in out.values()),
            "note": "Independent race Wilson intervals ignore same-day dependence; "
                    "use day-cluster bootstrap for promotion decisions. "
                    "Previously inspected years are retrospective, not forward validation."}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--races", required=True, type=int)
    p.add_argument("--winner-hits", required=True, type=int)
    p.add_argument("--ordered-hits", required=True, type=int)
    p.add_argument("--top3-hits", required=True, type=int)
    a = p.parse_args()
    print(json.dumps(evaluate({"winner_hit": a.winner_hits,
                               "ordered_all_hit": a.ordered_hits,
                               "top3_all_hit": a.top3_hits}, a.races),
                     ensure_ascii=False, indent=2))
