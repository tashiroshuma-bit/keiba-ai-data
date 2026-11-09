"""Prospective paired v50 vs v51-bodyweight rank evaluation, post-race only.

Input: archived capture (from capture_v50_bodyweight.py), official results
{"observed_at":"ISO8601","races":[{"race":"same key",
"finish_order":[1,2,3,...] }]}.
Do NOT use this script as a pre-off forecast entrypoint.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
try:
    from scripts.capture_v50_bodyweight import moment, immutable_save
    from scripts.v51_body_weight_shadow import apply
except ModuleNotFoundError:
    from capture_v50_bodyweight import moment, immutable_save
    from v51_body_weight_shadow import apply

def evaluate(archive,results,*,policy_path=None):
    if archive.get("schema")!="jra-v50-weight-paired-preoff-v1":
        raise ValueError("not a frozen standard v50/weight pair")
    ar={r["race"]:r for r in archive["races"]}
    rs=results.get("races")
    if not isinstance(rs,list) or len(ar)!=len(rs):
        raise ValueError("complete paired result set required")
    by={r["race"]:r for r in rs}
    if len(by)!=len(rs) or set(ar)!=set(by):
        raise ValueError("result race mismatch")
    obs=moment(results["observed_at"])
    records=[]
    for rid,r in sorted(ar.items()):
        off=moment(r["original_off_at"])
        if obs<=off:raise ValueError("official results cannot be known before race off")
        before=archive["forecast_asof"]
        base=[{"number":h["number"],"v50_p1":h["v50_p1"]} for h in r["horses"]]
        weights=[{"number":h["number"],"asof":before,
                  "weight_observed_at":h["weight_observed_at"],
                  "weight_change_bucket":h["weight_change_bucket"]} for h in r["horses"]]
        kwargs={"asof":before}
        if policy_path is not None:kwargs["policy_path"]=policy_path
        shadow=apply(base,weights,**kwargs)
        truth=[str(x) for x in by[rid]["finish_order"]]
        roster={str(h["number"]) for h in r["horses"]}
        if len(truth)!=len(roster) or len(set(truth))!=len(truth) or set(truth)!=roster:
            raise ValueError("complete ordered official finishing order required")
        p0={str(h["number"]):float(h["v50_p1"]) for h in base}
        p1={str(h["number"]):float(h["v51_shadow_p1"]) for h in shadow["horses"]}
        row={"race":rid,"race_date":rid[:10]}
        for label,p in (("v50",p0),("v51_shadow",p1)):
            ranked=sorted(roster,key=lambda k:(-round(p[k],12),int(k)))
            row[label]={"winner_hit":int(ranked[0]==truth[0]),
                "winner_in_top3":int(truth[0] in ranked[:3]),
                "unordered_podium_hit":int(set(ranked[:3])==set(truth[:3])),
                "ordered_podium_hit":int(ranked[:3]==truth[:3]),
                "logloss":-math.log(p[truth[0]]),
                "brier":sum((p[k]-int(k==truth[0]))**2 for k in roster)}
        records.append(row)
    metrics={}
    for label in ("v50","v51_shadow"):
        metrics[label]={metric:sum(row[label][metric] for row in records)/len(records)
                        for metric in records[0][label]}
    delta={k:metrics["v51_shadow"][k]-metrics["v50"][k] for k in metrics["v50"]}
    return {"status":"PAIRED_HISTORICAL_EVALUATION_NO_AUTOMATIC_PROMOTION",
            "evaluation_races":len(records),"metrics":metrics,"v51_minus_v50":delta,
            "source_database_sha256":archive["canonical_database_sha256"],
            "base_archive_sha256":archive.get("_file_sha256"),
            "limitations":["No independent publication authentication from JSON alone",
                           "Model promotion requires independent unseen date blocks and calibrated metrics",
                           "Ordered top3 here means p1-descending ranking, not joint triplet probability"],
            "race_details":records}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--archive",required=True)
    ap.add_argument("--official-results",required=True)
    ap.add_argument("--output",required=True)
    args=ap.parse_args()
    data=Path(args.archive).read_bytes()
    archive=json.loads(data)
    archive["_file_sha256"]=hashlib.sha256(data).hexdigest()
    result=evaluate(archive,json.loads(Path(args.official_results).read_bytes()))
    h=immutable_save(args.output,result)
    print(json.dumps({"races":result["evaluation_races"],"sha256":h,
                      "status":result["status"]}))

if __name__=="__main__":main()
