"""Research-only: retrain V51 historical rank model with pre-race-available past time/pace.
Usage: python scripts/v51_past_time_retrain.py --db canonical.sqlite --overlay review.sqlite --out metrics.json
Never use the target race's finish/time/odds. Every historical update occurs AFTER a whole race date.
"""
import argparse,collections,datetime,json,math,sqlite3
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
try:\n    from scripts.jra_historical_horse_id_ablation import build_dataset,create_feature_rows,_group_race_indices\nexcept ModuleNotFoundError:\n    from jra_historical_horse_id_ablation import build_dataset,create_feature_rows,_group_race_indices

# Explicit aliases, rather than guessing which numbers in a JSON payload are seconds.
TIME_KEYS=("finish_time_seconds","running_time_seconds","race_time_seconds","time_seconds")
LAST3_KEYS=("last_3f_seconds","last3f_seconds","closing_3f_seconds")
CORNER_KEYS=("corner4_position","fourth_corner_position")\nGOING_KEYS=("going","track_condition","ground_condition","馬場状態")
ADDITIONAL=("prior_time_per_100m","prior_last3f_seconds","prior_corner4_fraction","prior_time_count_log","prior_last3f_count_log","prior_corner_count_log","prior_track_surface_time_residual","prior_track_surface_going_time_residual","prior_track_surface_last3f_residual","prior_track_surface_going_last3f_residual")
def numeric(payload,keys,lo,hi):
    for key in keys:
        value=payload.get(key)
        if isinstance(value,(int,float)) and lo<=value<=hi and math.isfinite(value):
            return float(value)
        if isinstance(value,str):
            try:
                number=float(value.strip())
                if lo<=number<=hi and math.isfinite(number):return number
            except ValueError:pass
    return None

def build_past_features(db,races):
    c=sqlite3.connect("file:"+str(Path(db).resolve())+"?mode=ro",uri=True)
    ids=sorted(races)
    rows=collections.defaultdict(dict)
    for rid,hnum,payload in c.execute("select race_id,horse_number,payload_json from annual_report_runners"):
        if rid in races:
            try:rows[rid][int(hnum)]=json.loads(payload)
            except (TypeError,ValueError):pass
    c.close()
    # Use only previous dates; same-day results are never backfilled into earlier starts.
    by_date=collections.defaultdict(list)
    for rid,rr in races.items():by_date[rr[0]["date"]].append((rid,rr))
    histories=collections.defaultdict(lambda:collections.deque(maxlen=3))\n    track_bench=collections.defaultdict(lambda:collections.deque(maxlen=1000))\n    going_bench=collections.defaultdict(lambda:collections.deque(maxlen=1000))
    features={};coverage=collections.Counter()
    for date in sorted(by_date):
        pending=[]
        for rid,rr in sorted(by_date[date]):
            for runner in rr:
                key=(rid,int(runner["num"]))
                prior=list(histories[runner["horse_id"]])
                values=[]
                for field,default in (("time",0.0),("last3f",0.0),("corner",0.5)):
                    obs=[p[field] for p in prior if p[field] is not None]
                    values.append(float(np.mean(obs)) if obs else default)
                    coverage["prior_"+field+"_available"]+=bool(obs)
                residuals=[]\n                for field in ("time","last3f"):\n                    for bench in (track_bench,going_bench):\n                        obs=[p[field+"_residual_"+("track" if bench is track_bench else "going")] for p in prior if p.get(field+"_residual_"+("track" if bench is track_bench else "going")) is not None]\n                        residuals.append(float(np.mean(obs)) if obs else 0.0)\n                features[key]=[values[0],values[1],values[2],
                               math.log1p(sum(p["time"] is not None for p in prior)),
                               math.log1p(sum(p["last3f"] is not None for p in prior)),
                               math.log1p(sum(p["corner"] is not None for p in prior))]+residuals
                raw=rows[rid].get(int(runner["num"]),{})
                dist=float(runner["dist"])
                seconds=numeric(raw,TIME_KEYS,35,500)
                last3=numeric(raw,LAST3_KEYS,20,90)
                corner=numeric(raw,CORNER_KEYS,1,40)
                coverage["result_time_available"]+=seconds is not None
                coverage["result_last3f_available"]+=last3 is not None
                coverage["result_corner_available"]+=corner is not None
                pending.append((runner["horse_id"],{"time":100*seconds/dist if seconds and dist>0 else None,
                    "last3f":last3,"corner":corner/max(1,len(rr)) if corner else None}))
        for hid,key_track,key_going,item in pending:\n            histories[hid].append(item)\n            track_bench[key_track].append(item)\n            if key_going is not None:going_bench[key_going].append(item)
    return features,dict(coverage)

def fit(X,ranks,rids,train_ids,ridge=.1):
    groups=_group_race_indices(rids);ids=[rid for rid in groups if rid in train_ids]
    # Penalized race-wise conditional likelihood, one winner per race.
    sel=[groups[rid] for rid in ids]
    y=[int(np.where(ranks[idx]==1)[0][0]) for idx in sel]
    def objective(w):
        loss=0.;grad=np.zeros_like(w)
        for idx,truth in zip(sel,y):
            logits=X[idx]@w; logits-=logits.max();p=np.exp(logits);p/=p.sum()
            loss-=math.log(max(p[truth],1e-15))
            grad+=p@X[idx]-X[idx[truth]]
        return loss/len(sel)+ridge*(w@w)/2,grad/len(sel)+ridge*w
    result=minimize(objective,np.zeros(X.shape[1]),jac=True,method="L-BFGS-B",options={"maxiter":150})
    if not result.success and np.linalg.norm(result.jac)>1e-4:raise RuntimeError(str(result.message))
    return result.x

def evaluate(X,ranks,rids,ids,w):
    groups=_group_race_indices(rids);hits=0;loss=0.;brier=0.;n=0
    for rid in ids:
        idx=groups[rid];z=X[idx]@w;z-=z.max();p=np.exp(z);p/=p.sum()
        truth=int(np.where(ranks[idx]==1)[0][0]);hits+=int(np.argmax(p)==truth)
        loss-=math.log(max(p[truth],1e-15))
        y=np.zeros(len(p));y[truth]=1;brier+=float(np.sum((p-y)**2));n+=1
    return {"races":n,"top1_hits":hits,"top1_accuracy":hits/n,"logloss":loss/n,"brier":brier/n}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--db",required=True);ap.add_argument("--overlay",required=True);ap.add_argument("--out",required=True);args=ap.parse_args()
    races,_=build_dataset(args.db,args.overlay)
    base,ranks,rids,_,years,nums,_=create_feature_rows(races,"full")
    prior,coverage=build_past_features(args.db,races)
    extra=np.array([prior[(str(rid),int(num))] for rid,num in zip(rids,nums)],dtype=float)
    if coverage["prior_time_available"]<100 or coverage["prior_last3f_available"]<100:
        raise RuntimeError("Not enough genuine prior race time/last3f fields; inspect canonical payload keys, do not impute fake measurements: "+str(coverage))
    groups=_group_race_indices(rids)
    train={rid for rid,idx in groups.items() if years[idx[0]]<=2024}
    hold={rid for rid,idx in groups.items() if years[idx[0]]==2025}
    audit={rid for rid,idx in groups.items() if years[idx[0]]==2026}
    if not train or not hold:raise RuntimeError("Missing training/holdout cohort")
    train_idx=np.concatenate([groups[rid] for rid in sorted(train)])
    mu=base[train_idx].mean(0);sd=np.maximum(base[train_idx].std(0),1e-5)
    em=extra[train_idx].mean(0);es=np.maximum(extra[train_idx].std(0),1e-5)
    x0=(base-mu)/sd;x1=np.column_stack((x0,(extra-em)/es))
    result={"schema":"v51-past-time-retrain-research-v1","production_enabled":False,
            "features_added":list(ADDITIONAL),"coverage":coverage,
            "training_races":len(train),"holdout_2025_races":len(hold),"audit_2026_races":len(audit)}
    for label,X in (("baseline_31",x0),("plus_past_time_pace",np.column_stack((x0,(extra[:,:6]-em[:6])/es[:6]))),("plus_track_going_corrected",x1)):
        w=fit(X,ranks,rids,train)
        result[label]={"2025":evaluate(X,ranks,rids,sorted(hold),w),
                       "2026":evaluate(X,ranks,rids,sorted(audit),w) if audit else None,
                       "coefficients":w.tolist()}
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
