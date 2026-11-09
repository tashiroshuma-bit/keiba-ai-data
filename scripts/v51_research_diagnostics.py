"""Read-only v51 research diagnostics: full-field evidence and joint podium.

All data-bearing observations must precede forecast asof. No learned weight
changes or model promotion, no horse-name-based identity joins. Candidate
features are descriptive and must be fitted on strictly earlier data separately.
"""
import datetime as dt
import itertools
import math
from collections import defaultdict

def when(value):
    t=dt.datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if t.tzinfo is None:raise ValueError("timezone-aware timestamp required")
    return t.astimezone(dt.timezone.utc)

def safe(value):
    if value is None:return None
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):
        raise ValueError("finite numeric metric or null required")
    return float(value)

def audit_identity_field(rows,asof,off):
    a,o=when(asof),when(off)
    if not a<o: raise ValueError("not pre-off")
    if len(rows)<3:raise ValueError("at least 3 actual runners")
    seen=set()
    for h in rows:
        key=h.get("number")
        if type(key) is not int or key<=0 or key in seen:raise ValueError("number absent/duplicate")
        seen.add(key)
        proof=h.get("identity_evidence")
        if proof is None:
            if h.get("horse_id") is not None: raise ValueError("unproven horse ID")
            continue
        if not isinstance(proof,dict) or proof.get("horse_number")!=key or proof.get("horse_id")!=h.get("horse_id"):
            raise ValueError("official horse identity mismatch")
        if not str(proof.get("horse_id","")).startswith("jra:"):
            raise ValueError("official JRA horse ID proof required")
        if not str(proof.get("source_url","")).startswith("https://www.jra.go.jp/"):
            raise ValueError("source URL is not JRA primary evidence")
        if not isinstance(proof.get("source_sha256"),str) or len(proof["source_sha256"])!=64:
            raise ValueError("source hash absent")
        if when(proof["observed_at"])>a:raise ValueError("identity discovered after asof")
    return {"runners":len(rows),"verified_horse_ids":sum(bool(h.get("identity_evidence")) for h in rows),
            "missing_ids":sum(not bool(h.get("identity_evidence")) for h in rows)}

FEATURES=("horse_form","horse_class","opponent_strength","jockey_course_distance",
          "day_track_bias","rest_growth_bodyweight")
def preoff_feature_audit(rows,asof,off):
    identity=audit_identity_field(rows,asof,off)
    metrics={}
    for name in FEATURES:
        available=0
        for row in rows:
            field=row.get("research_features",{}).get(name)
            if field is None:continue
            if not isinstance(field,dict) or "observed_at" not in field or "value" not in field:
                raise ValueError(name+": value/observation metadata required")
            value=safe(field["value"])
            if when(field["observed_at"])>when(asof):
                raise ValueError(name+": future data leakage")
            if name in ("horse_form","horse_class","opponent_strength","jockey_course_distance"):
                if row.get("horse_id") is None or not row.get("identity_evidence"):
                    raise ValueError(name+": unverified horse identity")
            if name=="day_track_bias" and not field.get("earlier_race_evidence"):
                raise ValueError("day track bias requires earlier race evidence")
            if value is not None:available+=1
        metrics[name]={"observed":available,"missing":len(rows)-available,
                       "coverage":available/len(rows)}
    return {"status":"RESEARCH_FEATURE_COVERAGE_ONLY_NO_REWEIGHT",
            "identity":identity,"features":metrics}

def pl_podium(p1,horse_numbers):
    """Baseline PL joint top-three probabilities; NOT fitted p2/p3."""
    n=len(p1)
    if n!=len(horse_numbers) or n<3 or len(set(horse_numbers))!=n:
        raise ValueError("invalid joint podium roster")
    if any(safe(x) is None or x<=0 for x in p1) or abs(sum(p1)-1)>1e-7:
        raise ValueError("invalid first place distribution")
    ordered={}
    for i,j,k in itertools.permutations(range(n),3):
        prob=p1[i]*(p1[j]/(1-p1[i]))*(p1[k]/(1-p1[i]-p1[j]))
        ordered[(horse_numbers[i],horse_numbers[j],horse_numbers[k])]=prob
    if abs(sum(ordered.values())-1)>1e-7:
        raise ValueError("joint podium not normalized")
    marginal={number:{"p1":0.0,"p2":0.0,"p3":0.0} for number in horse_numbers}
    unordered=defaultdict(float)
    for triple,p in ordered.items():
        for m,number in enumerate(triple):marginal[number][("p1","p2","p3")[m]]+=p
        unordered[tuple(sorted(triple))]+=p
    best_order=max(ordered,key=lambda triple:(round(ordered[triple],12),tuple(-n for n in triple)))
    best_set=max(unordered,key=lambda triple:(round(unordered[triple],12),tuple(-n for n in triple)))
    return {"status":"PL_APPROXIMATION_NOT_LEARNED_CONDITIONAL_2ND_3RD",
            "ordered_best":list(best_order),"unordered_best":list(best_set),
            "ordered_best_probability":ordered[best_order],
            "unordered_best_probability":unordered[best_set],
            "marginal":{str(k):v for k,v in marginal.items()},
            "probability_sum":sum(ordered.values()),
            "candidate_2nd_3rd_training_complete":False}

def calibration_diagnostic(p1,horse_numbers):
    report=pl_podium(p1,horse_numbers)
    entropy=-sum(p*math.log(p) for p in p1)/math.log(len(p1))
    q=sorted(p1,reverse=True)
    report["uncertainty"]={"field_size":len(p1),"normalized_entropy":entropy,
                          "top1_probability":q[0],"top1_top2_gap":q[0]-q[1],
                          "calibration_verified":False}
    return report
