"""Reproducible same-race V50 vs V51 paired forecast validation.

Actual historical predictions MUST be frozen before off, with same asof,
exact horse number, name and official horse ID; every feature has a verified
source publication <= asof. Submitting fitted *weights* instead of a frozen
preoff prediction produces NO_ELIGIBLE_PAIRS, never artificial metrics.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import json
import math
import random
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_REPORT=ROOT/"reports/v51/v50_v51_paired_verification_status.json"
def parse(s):
    v=dt.datetime.fromisoformat(str(s).replace("Z","+00:00"))
    if v.tzinfo is None:raise ValueError("timestamp must have timezone")
    return v
def valid_horses(r,mark):
    hs=r.get("horses")
    if not isinstance(hs,list) or len(hs)<3:raise ValueError(mark+" missing complete field")
    n={int(h["number"]) for h in hs}
    if len(n)!=len(hs):raise ValueError(mark+" duplicate number")
    names={h["name"] for h in hs}
    if len(names)!=len(hs):raise ValueError(mark+" duplicate name")
    ids={h["horse_id"] for h in hs}
    if len(ids)!=len(hs) or any(not x.startswith("jra:") for x in ids):
        raise ValueError(mark+" missing official unique horse IDs")
    ps=[float(h["p1"]) for h in hs]
    if any(not math.isfinite(p) or p<=0 for p in ps) or abs(sum(ps)-1)>1e-6:
        raise ValueError(mark+" invalid probability distribution")
    for h in hs:
        if not h.get("horse_id_evidence_url") or not h.get("horse_id_evidence_sha256"):
            raise ValueError(mark+" official ID evidence missing")
        if not h.get("historical_feature_published_at"):
            raise ValueError(mark+" historical publication proof missing")
        if parse(h["historical_feature_published_at"])>parse(r["asof"]):
            raise ValueError(mark+" post-asof feature source")
    return hs
def joined(baseline,candidate,results):
    b={r["race"]:r for r in baseline.get("races",[])}
    c={r["race"]:r for r in candidate.get("races",[])}
    t={r["race"]:r for r in results.get("races",[])}
    if not b or not t:return [],{"reason":"missing official or baseline races","baseline":len(b),"candidate":len(c),"results":len(t)}
    match=[];reject=collections.Counter()
    for key,x in b.items():
        if key not in c:reject["missing_v51_preoff_snapshot"]+=1;continue
        if key not in t:reject["missing_official_full_result"]+=1;continue
        try:
            y=c[key];actual=t[key]
            if x.get("source_model")!="v50" or y.get("source_model")!="v51":
                raise ValueError("model version metadata invalid")
            off=parse(x["original_off_at"])
            if (parse(y["original_off_at"])!=off or parse(x["asof"])!=parse(y["asof"]) or
                parse(x["asof"])>=off):
                raise ValueError("pre-off asof/off mismatch")
            if not actual.get("official_sha256") or len(actual["official_sha256"])!=64:
                raise ValueError("official result evidence missing")
            bx=valid_horses(x,"v50");cy=valid_horses(y,"v51")
            m0={(h["number"],h["name"],h["horse_id"]) for h in bx}
            m1={(h["number"],h["name"],h["horse_id"]) for h in cy}
            if m0!=m1 or len(m0)!=actual["field_size"]:
                raise ValueError("identical number/name/horse ID rosters required")
            win=int(actual["winner_number"])
            if win not in {h["number"] for h in bx}:raise ValueError("winner outside roster")
            match.append((key,x,y,actual))
        except (ValueError,KeyError,TypeError) as e:
            reject[str(e)[:125]]+=1
    return match,dict(reject)
def metric(prediction,actual):
    hs=sorted(prediction["horses"],key=lambda h:(-h["p1"],h["number"]))
    winner=int(actual["winner_number"])
    p={h["number"]:h["p1"] for h in hs}
    return {"hit":int(hs[0]["number"]==winner),"top3":int(winner in [h["number"] for h in hs[:3]]),
            "logloss":-math.log(p[winner]),
            "brier":sum((q-(n==winner))**2 for n,q in p.items()),
            "top1":hs[0]["number"]}
def score(match):
    per=[]
    for key,b,c,truth in match:
        a=metric(b,truth);d=metric(c,truth)
        per.append({"race":key,"race_date":truth["date"],"base":a,"candidate":d,
                    "base_top_gap":sorted([h["p1"] for h in b["horses"]],reverse=True)[0]-
                                   sorted([h["p1"] for h in b["horses"]],reverse=True)[1],
                    "field_size":truth["field_size"]})
    n=len(per)
    summaries={}
    for label in ("base","candidate"):
        summaries[label]={"n":n,
         "hit":sum(v[label]["hit"] for v in per),
         "top3":sum(v[label]["top3"] for v in per),
         "mean_logloss":sum(v[label]["logloss"] for v in per)/n,
         "mean_brier":sum(v[label]["brier"] for v in per)/n}
    discordant={
        "base_only":sum(v["base"]["hit"] and not v["candidate"]["hit"] for v in per),
        "candidate_only":sum(v["candidate"]["hit"] and not v["base"]["hit"] for v in per)}
    a=discordant["base_only"];b=discordant["candidate_only"];k=a+b
    # exact two-sided binomial sign test for paired binary correctness
    pval=min(1.,2*sum(math.comb(k,i)*.5**k for i in range(min(a,b)+1))) if k else 1.
    # Block bootstrap by calendar date, so within-day dependencies are preserved.
    rng=random.Random(51)
    byday=collections.defaultdict(list)
    for v in per:byday[v["race_date"]].append(v)
    days=sorted(byday)
    boot=[]
    for _ in range(1000):
        rs=[x for day in [rng.choice(days) for _ in days] for x in byday[day]]
        boot.append(sum(x["candidate"]["hit"]-x["base"]["hit"] for x in rs)/len(rs))
    boot.sort()
    return {"status":"PAIRED_COMPLETE","n":n,
       "models":summaries,
       "discordant":discordant,"paired_exact_p_value":pval,
       "top1_hit_difference":(summaries["candidate"]["hit"]-summaries["base"]["hit"])/n,
       "top1_hit_diff_cluster_bootstrap_95pct":[boot[25],boot[975]],
       "subgroups":{
          name:{"n":len(group),
                "v50_hit":sum(v["base"]["hit"] for v in group),
                "v51_hit":sum(v["candidate"]["hit"] for v in group),
                "v50_top3":sum(v["base"]["top3"] for v in group),
                "v51_top3":sum(v["candidate"]["top3"] for v in group)}
          for name,group in {
              "close_top_gap_lt_2pp":[v for v in per if v["base_top_gap"]<.02],
              "large_field_ge_14":[v for v in per if v["field_size"]>=14],
              "other":[v for v in per if v["base_top_gap"]>=.02 and v["field_size"]<14]
          }.items()},
       "allow_promotion":(n>=100 and
          (summaries["candidate"]["hit"]>summaries["base"]["hit"]) and
          (summaries["candidate"]["top3"]>=summaries["base"]["top3"]) and
          (summaries["candidate"]["mean_logloss"]<=summaries["base"]["mean_logloss"]) and
          (summaries["candidate"]["mean_brier"]<=summaries["base"]["mean_brier"]) and
          boot[25]>0 and pval<.05)}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--baseline",required=True)
    p.add_argument("--candidate",required=True)
    p.add_argument("--results",required=True)
    p.add_argument("--output",default=str(DEFAULT_REPORT))
    a=p.parse_args()
    b=json.loads(Path(a.baseline).read_text())
    c=json.loads(Path(a.candidate).read_text())
    t=json.loads(Path(a.results).read_text())
    m,errors=joined(b,c,t)
    report=score(m) if m else {
      "status":"NO_ELIGIBLE_PAIRS","n":0,"allow_promotion":False,
      "not_an_accuracy_comparison":True}
    report["rejections"]=errors
    report["requirements"]=["exact_same_race_and_asof","preoff_proven_source",
        "complete_official_horse_ID","identical_horse_roster","full_JRA_result"]
    report["canonical_v50_changed"]=False
    path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(report,ensure_ascii=False))
if __name__=="__main__":
    main()
