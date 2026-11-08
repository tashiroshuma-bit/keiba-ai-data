"""Noncausal confidence checks for v50 race difficulty, research display only.

These are historical associations, not a calibrated probability of failure.
Designed to help audit weak shapes; never change p1/p2/p3 or betting picks.
"""
import math

def assess(model):
    horses=model.get("horses") or []
    if len(horses)<3 or len({h.get("number") for h in horses})!=len(horses):
        raise ValueError("unique complete race horses required")
    p=[h.get("p1") for h in horses]
    if any(not isinstance(x,(int,float)) or not math.isfinite(x) or x<=0 for x in p):
        raise ValueError("invalid preoff p1")
    if abs(sum(p)-1)>1e-6:raise ValueError("p1 probability not normalized")
    n=len(horses)
    q=sorted(p,reverse=True)
    e=-sum(x*math.log(x) for x in p)/math.log(n)
    gap=q[0]-q[1]
    flags=[name for name,ok in [
      ("LARGE_FIELD_14_PLUS",n>=14),
      ("LOW_MODEL_TOP1_UNDER_15PCT",q[0]<.15),
      ("MODEL_TOP_TWO_GAP_UNDER_2PP",gap<.02),
      ("HIGH_MODEL_ENTROPY_AT_LEAST_0_95",e>=.95)] if ok]
    return {"schema":"v50-race-difficulty-shadow-v1",
      "status":"RESEARCH_CAUTION_NOT_CALIBRATED",
      "features_available_preoff":{"runners":n,"max_model_p1":q[0],
        "max_vs_second_gap":gap,"normalized_entropy":e},
      "caution_flags":flags,
      "difficulty_level":"HIGH_REVIEW" if len(flags)>=2 else "SINGLE_MARKER" if flags else "NO_MARKERS",
      "ranking_modified":False,"boosted_longshots":False,
      "rare_upset_predicted":False,
      "evidence":"reports/v50/retrained_canonical_db_v10_horse_jockey_research.md",
      "limitations":"Thresholds are descriptive and not a validated v50 failure classifier."}
