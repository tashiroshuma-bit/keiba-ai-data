"""Statistical paired historical validation: choose temperature on earlier period only.

Input {"records":[{"race_id":str,"date":"YYYY-MM-DD","partition":"calibration"|"test",
"winner":int,"v49":{horse_number:prob},"v50":{horse_number:prob}},...]}
The input MUST contain genuine independently sourced as-of v49/v50 probabilities;
this program never invents them. Fail closed on overlaps and invalid forecasts.
"""
import argparse, collections, json, math, random

def normalize(values,t):
    weights={k:math.log(v)/t for k,v in values.items()}
    peak=max(weights.values())
    exp={k:math.exp(v-peak) for k,v in weights.items()}
    mass=sum(exp.values())
    return {k:v/mass for k,v in exp.items()}

def validate(records):
    seen=set()
    for r in records:
        rid=r["race_id"]
        if rid in seen: raise ValueError("duplicate race_id")
        seen.add(rid)
        if r["partition"] not in ("calibration","test"):raise ValueError("partition")
        if r["date"][:4] not in ("2025","2026"):raise ValueError("unsupported year")
        if (r["partition"]=="calibration")!=(r["date"][:4]=="2025"):
            raise ValueError("calibration must be 2025, test 2026")
        a={str(k):float(v) for k,v in r["v49"].items()}
        b={str(k):float(v) for k,v in r["v50"].items()}
        if set(a)!=set(b) or str(r["winner"]) not in a or len(a)<3:
            raise ValueError("different field or invalid winner")
        for vals in (a,b):
            if any(not math.isfinite(x) or x<=0 for x in vals.values()) or abs(sum(vals.values())-1)>1e-5:
                raise ValueError("invalid probabilities")
    if not any(r["partition"]=="calibration" for r in records) or not any(r["partition"]=="test" for r in records):
        raise ValueError("both periods required")

def score(records, model, temperature):
    losses=[]; briers=[]; hits=[]
    for r in records:
        p=normalize({str(k):float(v) for k,v in r[model].items()},temperature)
        actual=str(r["winner"])
        losses.append(-math.log(p[actual]))
        briers.append(sum((v-(k==actual))**2 for k,v in p.items()))
        hits.append(int(max(sorted(p),key=p.get)==actual))
    return {"n":len(records),"top1_hits":sum(hits),"top1_rate":sum(hits)/len(hits),
            "log_loss":sum(losses)/len(losses),"brier":sum(briers)/len(briers)}

def report(records):
    validate(records)
    train=[r for r in records if r["partition"]=="calibration"]
    test=[r for r in records if r["partition"]=="test"]
    grid=(0.7,0.8,0.9,1.0,1.1,1.25,1.5,1.75,2.0)
    temp=min(grid,key=lambda t:(score(train,"v50",t)["log_loss"],abs(t-1)))
    baseline=score(test,"v49",1.0)
    candidate=score(test,"v50",temp)
    days=collections.defaultdict(list)
    for r in test:days[r["date"]].append(r)
    keys=sorted(days);rng=random.Random(20261102);deltas=[]
    for _ in range(2000):
        sample=[r for day in (rng.choice(keys) for _ in keys) for r in days[day]]
        deltas.append(score(sample,"v50",temp)["top1_rate"]-score(sample,"v49",1)["top1_rate"])
    deltas.sort()
    return {"schema":"v50-paired-historical-validation-v1","calibration_period":"2025",
            "test_period":"2026","calibration_races":len(train),"test_races":len(test),
            "temperature_selected_on_2025":temp,"v49_2026":baseline,"v50_2026":candidate,
            "delta_top1_95pct_day_bootstrap":[deltas[49],deltas[1949]],
            "limitations":"Only valid if input full cards, identities, outcomes and historical as-of timestamps were independently authenticated. No post-test parameter selection.",
            "production_promoted":False}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--paired",required=True);p.add_argument("--out",required=True)
    a=p.parse_args()
    result=report(json.load(open(a.paired,encoding="utf-8"))["records"])
    with open(a.out,"w",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2))
