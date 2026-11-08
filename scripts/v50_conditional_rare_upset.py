"""Strictly conditional v50 rare-upset WATCH, not an always-on horse boost.

Research signal is calculated entirely from an already frozen race model
before off. No past result/podium popularity enters the signal. Submodel
activation is forbidden until independent chronological replay succeeds on
canonical v50 predictions; default is the unchanged canonical distribution.
"""
import math
from pathlib import Path
import json

def assessment(model, policy, *, extended=None):
    horses=model.get("horses")
    if not isinstance(horses,list) or len(horses)<3:
        raise ValueError("complete preoff v50 horse model required")
    probs=[h.get("p1") for h in horses]
    if any(not isinstance(p,(int,float)) or not math.isfinite(p) or p<=0 or p>=1 for p in probs):
        raise ValueError("invalid v50 probabilities")
    if abs(sum(probs)-1)>1e-7 or len({h["number"] for h in horses})!=len(horses):
        raise ValueError("invalid total probability/roster")
    n=len(probs)
    order=sorted(probs,reverse=True)
    entropy=-sum(p*math.log(p) for p in probs)/math.log(n)
    f={"field_size":n,"candidate_max_p1":order[0],
       "candidate_gap_1_2":order[0]-order[1],
       "candidate_entropy":entropy}
    def matches(rule):
        if not isinstance(rule,dict):return False
        keys=("min_field","max_top1","max_gap","min_entropy")
        if not all(k in rule and isinstance(rule[k],(int,float)) and math.isfinite(rule[k]) for k in keys):
            raise ValueError("invalid rare-event rule")
        return n>=rule["min_field"] and order[0]<=rule["max_top1"] and (
            order[0]-order[1])<=rule["max_gap"] and entropy>=rule["min_entropy"]
    def validated(policy):
        stats=policy.get("candidate_holdout") or {}
        # No activation on archive proxy alone; require independent v50 test.
        return (policy.get("enabled") is True
          and policy.get("model_family_validated")=="canonical_v50"
          and policy.get("reviewed_on_independent_dates") is True
          and isinstance(stats,dict)
          and stats.get("extreme_upsets",0)>=3
          and stats.get("extreme_hits",0)>=2
          and stats.get("flag_rate",1)>0
          and stats.get("flag_rate",1)<=.15
          and stats.get("lift_vs_base",0)>=2)
    extreme_watch=matches(policy.get("candidate_rule"))
    extended_watch=matches((extended or {}).get("selected"))
    active=bool(extreme_watch and validated(policy))
    # The context-specific decision is additional review/uncertainty warning.
    # No horse's probabilities, ordering or PL ticket math are touched.
    return {"schema":"v50-conditional-rare-upset-research-v1",
      "features_from_frozen_preoff_p1":f,
      "extreme_2025_criteria_match":extreme_watch,
      "extended_2025_criteria_match":extended_watch,
      "rare_upset_model_activation_allowed":active,
      "mode":"RARE_UPSET_REVIEW" if active else "STANDARD_V50",
      "research_watch_only":bool((extreme_watch or extended_watch) and not active),
      "canonical_distribution_unchanged":True,
      "caution":"Rare upset is a historical *event*, not an identifiable horse without independent preoff validation.",
      "probability_boost_applied":False,
      "event_label_popularity_never_used_as_feature":True}

def from_files(model,policy_path,extended_path=None):
    policy=json.loads(Path(policy_path).read_text())
    extended=json.loads(Path(extended_path).read_text()) if extended_path and Path(extended_path).exists() else None
    return assessment(model,policy,extended=extended)
