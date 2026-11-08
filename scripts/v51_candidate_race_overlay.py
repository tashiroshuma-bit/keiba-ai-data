"""V51 conditional horse ranking candidate; fail-closed shadow overlay on v50.

Inputs per race: a complete frozen v50 p1 field and one evidence-backed
34-feature vector for every EXACT horse number+official ID. Historic source
observed/published timestamps must precede forecast time, and race off time
must follow forecast. Production canonical probability is NEVER overwritten.
"""
from __future__ import annotations
import json,math
from pathlib import Path
try:
    from scripts.v51_preoff_provenance_guard import (strict_time,
        check_historical_observation,match_horse_identity)
except ModuleNotFoundError:
    from v51_preoff_provenance_guard import (strict_time,
        check_historical_observation,match_horse_identity)

def softmax(values):
    peak=max(values)
    ex=[math.exp(x-peak) for x in values]
    return [x/sum(ex) for x in ex]

def overlay(v50_model, source, model_file, *, research_alpha=0.0):
    fitted=json.loads(Path(model_file).read_text())
    if fitted.get("production_enabled") is not False or fitted.get("version")!="v51":
        raise ValueError("V51 candidate policy must be explicitly research-only")
    if not isinstance(research_alpha,(int,float)) or not 0<=research_alpha<=1:
        raise ValueError("valid research alpha between 0 and 1 required")
    v50=v50_model["horses"]
    if not v50 or len(v50)<3:
        raise ValueError("empty v50 field")
    original={int(h["number"]):float(h["p1"]) for h in v50}
    if len(original)!=len(v50) or abs(sum(original.values())-1)>1e-6:
        raise ValueError("v50 roster probability invalid")
    other=source.get("horses")
    if not isinstance(other,list) or len(other)!=len(v50):
        raise ValueError("complete horse feature field required")
    lookup={int(h["number"]):h for h in other}
    if len(lookup)!=len(other) or set(lookup)!=set(original):
        raise ValueError("v51 source/field mismatch")
    asof=strict_time(source["forecast_asof"])
    off=strict_time(source["race_off_at"])
    if not asof<off:
        raise ValueError("forecast at or after off")
    idx=fitted["feature_indices"]
    dim=fitted["feature_count"]
    weights=fitted["weights"]
    mean=fitted["mean"];scale=fitted["scale"]
    if len(weights)!=len(idx) or len(scale)!=dim or len(mean)!=dim:
        raise ValueError("fitted v51 coefficient schema corrupt")
    scores=[];identity_coverage=0
    for h in v50:
        item=lookup[int(h["number"])]
        check_historical_observation(item["feature_evidence"],
           race_off_at=source["race_off_at"],forecast_asof=source["forecast_asof"])
        horse_id=match_horse_identity({
             "race_id":source["race_id"],"horse_number":h["number"],
             "horse_name":h["name"]},item["official_identity_proof"])
        if horse_id!=item.get("horse_id"):
            raise ValueError("source horse ID does not match official proof")
        identity_coverage+=1
        x=item.get("feature_values")
        if not isinstance(x,list) or len(x)!=dim or any(
             not isinstance(t,(int,float)) or not math.isfinite(t) for t in x):
            raise ValueError("complete finite 34 preoff historical features required")
        scores.append(sum(weights[k]*(x[j]-mean[j])/scale[j]
                      for k,j in enumerate(idx)))
    new=softmax(scores)
    mix=softmax([(1-research_alpha)*math.log(original[int(h["number"])])
                 +research_alpha*math.log(p)
                 for h,p in zip(v50,new)])
    ranked=sorted([{"number":h["number"],"name":h["name"],
        "v50_p1":original[int(h["number"])],
        "v51_candidate_p1":q,"shadow_ensemble_p1":r}
          for h,q,r in zip(v50,new,mix)],
        key=lambda h:-h["shadow_ensemble_p1"])
    return {"version":"v51",
       "status":"RESEARCH_ONLY_FITTED_CANDIDATE_FAILS_OOS_GATE",
       "field_size":len(v50),"evidence_backed_ids":identity_coverage,
       "research_alpha":research_alpha,
       "rankings":ranked,
       "v50_original_unchanged":True,
       "research_only":True,
       "production_promotion":False}
