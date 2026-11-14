"""Official v51 rank forecast: no v50 predictions, overlays or fallback.

Accept only verified point-in-time 31-feature full-roster snapshots backed by
canonical v12, official identity proofs and historical publication evidence.
This is an inference entrypoint, not a data collection service.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

try:
    from scripts.v51_recovered_id_conditional_rank import make_race_probabilities, softmax
    from scripts.v51_preoff_provenance_guard import check_historical_observation
except ModuleNotFoundError:
    from v51_recovered_id_conditional_rank import make_race_probabilities, softmax
    from v51_preoff_provenance_guard import check_historical_observation

ROOT=Path(__file__).resolve().parents[1]
POLICY=ROOT/"operations/prediction_policy/standard_v51.json"
MODEL=ROOT/"operations/prediction_policy/standard_v51_model.json"
STATE=ROOT/"PROJECT_STATE.json"

def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()

def stamp(value):
    x=dt.datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if x.tzinfo is None:raise ValueError("timezone-aware point-in-time required")
    return x

def valid_sha(value):
    return isinstance(value,str) and len(value)==64 and all(c in "0123456789abcdef" for c in value.lower())

def evidence_guard(h,asof,off):
    proof=h.get("official_identity_proof")
    if not isinstance(proof,dict):raise ValueError("official horse ID evidence missing")
    if proof.get("horse_id")!=h.get("horse_id") or proof.get("horse_number")!=h["number"]:
        raise ValueError("official horse ID evidence mismatch")
    if not str(h["horse_id"]).startswith("jra:"):
        raise ValueError("official JRA horse ID required")
    source = urlparse(str(proof.get("source_url", "")))
    if source.scheme != "https" or source.hostname not in {"www.jra.go.jp", "jra.go.jp", "sp.jra.jp", "app.jra.jp"} or not valid_sha(proof.get("source_sha256")):
        raise ValueError("official JRA evidence URL and SHA256 required")
    if stamp(proof["observed_at"])>asof or stamp(h["features_observed_at"])>asof:
        raise ValueError("feature or identity evidence after prediction asof")
    if "features_generated_at" in h and stamp(h["features_generated_at"])>asof:
        raise ValueError("features generated after prediction asof")
    history=h.get("historical_evidence",[])
    starts=h.get("prior_starts")
    if type(starts) is not int or starts<0:
        raise ValueError("validated nonnegative prior_starts required")
    if starts>0 and not history:
        raise ValueError("historical source publication evidence required for trained features")
    for item in history:
        check_historical_observation(item,race_off_at=off.isoformat(),forecast_asof=asof.isoformat())
    previous=h.get("latest_history_date")
    local_off=off.astimezone(dt.timezone(dt.timedelta(hours=9))).date()
    if starts and (previous is None or str(previous)>=local_off.isoformat()):
        raise ValueError("race-date historical lookahead or absent prior history")
    if not starts and previous is not None:
        raise ValueError("debut runner has incompatible history date")

def combinations(z,numbers,cal,limit):
    raw=softmax(z[0])
    cls=("high_entropy" if -float(np.sum(raw*np.log(np.maximum(1e-15,raw))))/math.log(len(raw))>=cal["group_entropy_cutoff"] else "other_entropy")
    cls+="__"+("close_field" if float(max(raw))<cal["group_favorite_cutoff"] else "clear_favorite")
    t1=cal["winner_entropy_confidence_groups"][cls]["temp"]
    p1=softmax(z[0],t1)
    t2=cal["global_stage_temperatures"]["2"]
    t3=cal["global_stage_temperatures"]["3"]
    ordered=[]
    unordered=collections.defaultdict(float)
    for i in range(len(numbers)):
        second=[j for j in range(len(numbers)) if j!=i]
        p2=softmax(z[1][second],t2)
        for j_index,j in enumerate(second):
            third=[k for k in range(len(numbers)) if k!=i and k!=j]
            p3=softmax(z[2][third],t3)
            for k_index,k in enumerate(third):
                p=float(p1[i]*p2[j_index]*p3[k_index])
                a=(numbers[i],numbers[j],numbers[k])
                ordered.append((p,a))
                unordered[tuple(sorted(a))]+=p
    mass=sum(x for x,_ in ordered)
    if not abs(mass-1.0)<1e-8:raise ValueError("three-stage joint mass is not one")
    ordered.sort(key=lambda r:(-r[0],r[1]))
    un=sorted(unordered.items(),key=lambda r:(-r[1],r[0]))
    return {"ordered_total":len(ordered),"unordered_total":len(un),"mass":mass,
      "top_ordered":[{"numbers":list(a),"probability":p} for p,a in ordered[:limit]],
      "top_unordered":[{"numbers":list(a),"probability":p} for a,p in un[:limit]]}

def forecast(snapshot_path,database_path,output_path,*,state_path=STATE,
             policy_path=POLICY,model_path=MODEL,top_combinations=20):
    out=Path(output_path)
    if out.exists():raise FileExistsError("official forecast cannot overwrite existing file")
    state=json.loads(Path(state_path).read_bytes())
    policy=json.loads(Path(policy_path).read_bytes())
    model=json.loads(Path(model_path).read_bytes())
    current=state.get("standard_forecast",{})
    if (current.get("version")!="v51" or current.get("policy")!="operations/prediction_policy/standard_v51.json"
        or current.get("entrypoint")!="scripts/standard_v51_forecast.py" or not current.get("adopted_by_user")):
        raise ValueError("v51 official state routing mismatch")
    if policy.get("standard_version")!="v51" or policy.get("standard_for_future_races") is not True or policy.get("v50_fallback") is not False:
        raise ValueError("v51 official policy is not active")
    if policy.get("live_bet_generation") is not False:
        raise ValueError("unauthorized live-bet generation")
    expected=policy["expected_canonical_db_sha256"]
    if state["database"]["sha256"]!=expected or model.get("canonical_db_sha256")!=expected:
        raise ValueError("official v12 canonical database mismatch")
    if digest(database_path)!=expected:raise ValueError("source SQLite hash mismatch")
    if model.get("production_enabled") is not True or model.get("mode")!="full" or model.get("feature_count")!=31:
        raise ValueError("approved full v51 model required")
    features=np.array(model["stage_coefficients"],dtype=float)
    mean=np.array(model["feature_mean"],dtype=float)
    scale=np.array(model["feature_scale"],dtype=float)
    if features.shape!=(3,31) or mean.shape!=(31,) or scale.shape!=(31,) or not np.isfinite(features).all() or not np.isfinite(mean).all() or not np.isfinite(scale).all() or np.any(scale<=0):
        raise ValueError("invalid trained v51 model")
    doc=json.loads(Path(snapshot_path).read_bytes())
    if (doc.get("schema")!=policy["requires_feature_schema"] or
        doc.get("canonical_database_sha256")!=expected):
        raise ValueError("validated full-field preoff snapshot schema and canonical SHA required")
    if not valid_sha(doc.get("roster_source_sha256")) or not str(doc.get("roster_source_url","")).startswith("https://"):
        raise ValueError("original preoff racecard source evidence required")
    asof=stamp(doc["forecast_asof"])
    if stamp(doc["roster_captured_at"])>asof:
        raise ValueError("racecard was observed after forecast")
    if not isinstance(doc.get("races"),list) or not doc["races"]:
        raise ValueError("empty official race set")
    identifiers=set()
    res=[]
    for race in doc["races"]:
        rid=race["race"]
        if rid in identifiers:raise ValueError("duplicate race")
        identifiers.add(rid)
        off=stamp(race["race_off_at"])
        if not (asof<off):raise ValueError("race is not before off")
        if stamp(race["features_generated_at"])>asof:raise ValueError("features created after forecast")
        horses=race.get("horses")
        if not isinstance(horses,list) or len(horses)<3:raise ValueError("full field (3+) missing")
        nos=[h["number"] for h in horses]
        if any(type(n) is not int or n<1 for n in nos) or len(nos)!=len(set(nos)):
            raise ValueError("invalid or duplicate runner number")
        if len({h["horse_id"] for h in horses})!=len(horses):
            raise ValueError("duplicate official horse ID")
        horses=sorted(horses,key=lambda h:h["number"])
        vals=[]
        for h in horses:
            if not isinstance(h.get("name"),str) or not h["name"].strip():
                raise ValueError("runner name missing")
            evidence_guard(h,asof,off)
            row=h.get("feature_values")
            if not isinstance(row,list) or len(row)!=31 or any(type(v) not in (float,int) or not math.isfinite(v) for v in row):
                raise ValueError("31 observed finite features required")
            vals.append(row)
        z=[(np.array(vals,dtype=float)-mean)/scale@coef for coef in features]
        prob=make_race_probabilities(z,model["calibration"])
        combos=combinations(z,[h["number"] for h in horses],model["calibration"],top_combinations)
        if not all(abs(float(prob[k].sum())-1)<1e-8 for k in ("p1","p2","p3")):
            raise ValueError("normalized runner positions required")
        res.append({"race":rid,"race_off_at":race["race_off_at"],
          "runners":[{"number":h["number"],"name":h["name"],"horse_id":h["horse_id"],
             "p1":float(prob["p1"][i]),"p2":float(prob["p2"][i]),
             "p3":float(prob["p3"][i]),"p_top3":float(prob["top3_sum"][i])}
                for i,h in enumerate(horses)],
          "ordered_top3":[horses[i]["number"] for i in prob["ordered_pick"]],
          "unordered_top3":sorted(horses[i]["number"] for i in prob["unordered_pick"]),
          "ordered_top3_probability":float(prob["ordered_pick_probability"]),
          "unordered_top3_probability":float(prob["unordered_pick_probability"]),
          "normalized_entropy":float(prob["entropy"]),"stratum":prob["calibration_stratum"],
          "combination_audit":combos})
    answer={"schema":"jra-v51-official-forecast-v1","version":"v51","status":"OFFICIAL_IF_EVIDENCE_VERIFIED",
      "forecast_asof":doc["forecast_asof"],"canonical_db_sha256":expected,
      "input_sha256":digest(snapshot_path),"model_sha256":digest(model_path),
      "races":res,"v50_used":False,"no_live_bets":True,
      "qualifiers":["This output is only valid for externally evidenced source timestamps and full fields.",
                    "Historical retrospective 2026 evaluation does not prove future result accuracy.",
                    "Model calibrated on 2025; latest frozen 2026 winner ECE=0.02763."]}
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x",encoding="utf-8") as f:
        json.dump(answer,f,ensure_ascii=False,indent=2)
        f.write("\n")
    return answer

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--features",required=True)
    parser.add_argument("--database",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--top-combinations",type=int,default=20)
    args=parser.parse_args()
    result=forecast(args.features,args.database,args.output,
                    top_combinations=args.top_combinations)
    print(json.dumps({"model":result["version"],"races":len(result["races"]),
       "output":args.output,"v50_used":False},ensure_ascii=False))

if __name__=="__main__":main()
