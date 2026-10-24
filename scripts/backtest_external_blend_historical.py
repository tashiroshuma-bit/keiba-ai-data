#!/usr/bin/env python3
"""Leakage-safe historical evaluation of internal/external JRA model blends.

Input JSONL per race:
{"race_id":"2026-10-18-KYO-11","off_at":"2026-10-18T15:40:00+09:00",
 "internal_captured_at":"2026-10-18T08:00:00+09:00",
 "external_captured_at":"2026-10-18T08:15:00+09:00",
 "external_page_updated_at":"2026-10-17T12:00:00+09:00",
 "internal_model_trained_through":"2026-10-01T00:00:00+09:00",
 "horses":[{"number":1,"internal_p1":0.2,"external_index":80},...],
 "finish":[3,1,2]}

No outcome labels may be used in training/reweighting; race records must
represent an authentic pre-off snapshot, not retrospective reconstruction.
"""
import argparse
from datetime import datetime,timedelta
import json, math
from pathlib import Path
from collections import defaultdict

WEIGHTS=(0,.1,.25,.5,.75,1)
TEMPERATURES=(10,20,40)
EPS=1e-12

def stamp(v):
    t=datetime.fromisoformat(v)
    if t.utcoffset() is None:raise ValueError("Naive timestamp")
    return t

def validate(row):
    off=stamp(row["off_at"])
    for field in ("internal_captured_at","external_captured_at","external_page_updated_at","internal_model_trained_through"):
        if stamp(row[field])>=off-timedelta(minutes=5):
            raise ValueError("Future or too-late information: "+field)
    if stamp(row["internal_model_trained_through"])>stamp(row["internal_captured_at"]):
        raise ValueError("Model training cutoff exceeds prediction time")
    h=row["horses"];ns=[int(x["number"]) for x in h]
    if len(ns)!=len(set(ns)) or len(ns)<3:raise ValueError("Bad roster")
    if not all(math.isfinite(float(x["internal_p1"])) and 0<float(x["internal_p1"])<1 and math.isfinite(float(x["external_index"])) for x in h):
        raise ValueError("Bad probability/index")
    if abs(sum(float(x["internal_p1"]) for x in h)-1)>1e-5:
        raise ValueError("Internal probabilities not normalized")
    finish=list(map(int,row["finish"]))
    if len(finish)<3 or len(set(finish))!=len(finish) or any(x not in ns for x in finish[:3]):
        raise ValueError("Bad finish")
    return row

def probs(h,w,t):
    raw=[float(x["external_index"]) for x in h]
    mx=max(raw);ex=[math.exp((v-mx)/t) for v in raw];total=sum(ex)
    return [(1-w)*float(x["internal_p1"])+w*(z/total) for x,z in zip(h,ex)]

def score(row,w,t):
    h=row["horses"];ns=[int(x["number"]) for x in h];p=probs(h,w,t)
    order=sorted(range(len(ns)),key=lambda i:(-p[i],ns[i]))
    winner=int(row["finish"][0]);i=ns.index(winner)
    hit=int(ns[order[0]]==winner)
    brier=sum((pi-(int(n==winner)))**2 for n,pi in zip(ns,p))
    logloss=-math.log(max(EPS,p[i]))
    return dict(hit=hit,brier=brier,logloss=logloss)

def mean(xs,key):
    return sum(x[key] for x in xs)/len(xs)

def run(path,min_races):
    accepted=[];rejected=[];seen=set()
    for line_no,line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(),1):
        if not line.strip():continue
        try:
            row=validate(json.loads(line))
            if row["race_id"] in seen:raise ValueError("Duplicate race_id")
            seen.add(row["race_id"]);accepted.append(row)
        except (ValueError,KeyError,TypeError) as e:
            rejected.append({"line":line_no,"reason":str(e)})
    accepted.sort(key=lambda r:stamp(r["off_at"]))
    result={"status":"INSUFFICIENT_HISTORICAL_PREOFF_DATA","accepted_races":len(accepted),
            "rejected":rejected,"min_races":min_races,"scores":[],"best":None}
    if len(accepted)<min_races:return result
    # Chronological split: choose model hyperparameters on the oldest 70%,
    # then report untouched newest 30%. Never select by the test results.
    cut=int(len(accepted)*.7)
    train,test=accepted[:cut],accepted[cut:]
    for t in TEMPERATURES:
        for w in WEIGHTS:
            tr=[score(r,w,t) for r in train]
            te=[score(r,w,t) for r in test]
            result["scores"].append({"weight":w,"temperature":t,
                "train_n":len(train),"test_n":len(test),
                "train_top1":mean(tr,"hit"),"test_top1":mean(te,"hit"),
                "train_brier":mean(tr,"brier"),"test_brier":mean(te,"brier"),
                "train_logloss":mean(tr,"logloss"),"test_logloss":mean(te,"logloss")})
    best=min(result["scores"],key=lambda x:(x["train_logloss"],x["train_brier"]))
    baseline=next(x for x in result["scores"] if x["weight"]==0 and x["temperature"]==20)
    result["selected_on_train"]={"weight":best["weight"],"temperature":best["temperature"]}
    result["holdout_vs_internal"]={
        "delta_logloss":best["test_logloss"]-baseline["test_logloss"],
        "delta_brier":best["test_brier"]-baseline["test_brier"],
        "delta_top1_hit":best["test_top1"]-baseline["test_top1"],
    }
    result["status"]="HOLDOUT_EVALUATED_NOT_AUTOMATICALLY_PRODUCTION_APPROVED"
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument("--input",required=True);p.add_argument("--out",required=True);p.add_argument("--min-races",type=int,default=100)
    args=p.parse_args();res=run(args.input,args.min_races)
    Path(args.out).parent.mkdir(parents=True,exist_ok=True)
    Path(args.out).write_text(json.dumps(res,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":res["status"],"accepted":res["accepted_races"],"rejected":len(res["rejected"]),"best":res["best"]},ensure_ascii=False))
    if res["status"]=="INSUFFICIENT_HISTORICAL_PREOFF_DATA":raise SystemExit(2)
if __name__=="__main__":main()
