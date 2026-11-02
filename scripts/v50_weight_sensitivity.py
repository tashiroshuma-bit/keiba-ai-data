"""Sensitivity of v50 baseline-A plus rider-residual blend.

Weights scale rider residual in log-odds: w=0 means A-only (at T=1), w=1
current v50. Do not interpret w as a linear 0-100% probability mixture.
Select weight and temperature on Oct31 only; Nov01 is untouched holdout.
"""
import json, math, random
from scripts.v50_two_day_real_calibration import SNAP, CAT, get_oct, get_nov, corrected, metrics

WEIGHTS=(0,0.25,0.5,0.75,1,1.5,2,3,4)
TEMPERATURES=(0.7,0.8,0.9,1.0,1.1,1.25,1.5,1.75,2.0)

def run():
    snap=json.loads(SNAP.read_text()); cat=json.loads(CAT.read_text())
    if snap["database_sha256"]!=cat["database_sha256"]:raise ValueError("different sources")
    residuals=snap["residuals"]
    calibration=get_oct({name:jid for jid,name in cat["direct_identity_catalog"]})
    holdout=get_nov()
    table=[]
    for weight in WEIGHTS:
        for temp in TEMPERATURES:
            a=metrics(calibration,residuals,weight,temp)
            b=metrics(holdout,residuals,weight,temp)
            table.append({"weight":weight,"temperature":temp,"calibration":a,"holdout":b})
    select=min(table,key=lambda r:(r["calibration"]["mean_log_loss"],r["calibration"]["mean_brier"],abs(r["weight"]-1),abs(r["temperature"]-1)))
    ref=next(x for x in table if x["weight"]==0 and x["temperature"]==1)
    old=next(x for x in table if x["weight"]==1 and x["temperature"]==0.7)
    at_fixed_temp=[next(x for x in table if x["weight"]==w and x["temperature"]==0.7) for w in WEIGHTS]
    at_no_temp=[next(x for x in table if x["weight"]==w and x["temperature"]==1) for w in WEIGHTS]
    rank_changes=[]
    for w in WEIGHTS:
        changed=0
        gained=lost=0
        for r in holdout:
            base=r["p1"]; adj=corrected(base,r["jockey_ids"],r["surface"],residuals,w,0.7)
            k0=max(sorted(base),key=base.get);k1=max(sorted(adj),key=adj.get)
            if k0!=k1:
                changed+=1;gained+=int(k1==r["winner"]);lost+=int(k0==r["winner"])
        rank_changes.append({"weight":w,"different_winner_picks":changed,"gained_winners":gained,"lost_winners":lost})
    # Paired race CI for the selected rule; optimistic conditioning on 10/31 is not covered.
    rng=random.Random(20261102)
    per_race=[]
    for r in holdout:
        p=corrected(r["p1"],r["jockey_ids"],r["surface"],residuals,select["weight"],select["temperature"])
        q=r["p1"];truth=r["winner"]
        per_race.append({"ll":math.log(q[truth])-math.log(p[truth]),
          "brier":sum((v-(k==truth))**2 for k,v in p.items())-sum((v-(k==truth))**2 for k,v in q.items()),
          "hit":int(max(sorted(p),key=p.get)==truth)-int(max(sorted(q),key=q.get)==truth)})
    cis={}
    for metric in ("ll","brier","hit"):
        sampled=sorted(sum(per_race[rng.randrange(len(per_race))][metric] for _ in per_race)/len(per_race) for __ in range(3000))
        cis[metric]=[sampled[74],sampled[2924]]
    return {"schema":"v50-historical-weight-sensitivity-v1","baseline":"internal A",
            "formula":"p_i proportional to exp((log(pA_i)+weight*rider_residual_i)/temperature)",
            "selection":"Grid selected on 2026-10-31 (23 races) by minimum Log Loss; 2026-11-01 (23 races) is held out",
            "source_db_sha256":snap["database_sha256"],"rider_history_races":snap["races_used"],
            "current_policy":{"weight":1,"temperature":0.7},
            "baseline_reference":ref,"current_policy_metrics":old,
            "selected_from_oct31":select,
            "selection_holdout_delta95_bootstrap":cis,
            "weight_sweep_at_temperature_0_7":at_fixed_temp,
            "weight_sweep_at_temperature_1_0":at_no_temp,
            "winner_pick_change_versus_A":rank_changes,
            "limitations":["only 23 races per split","2026-10-31 outcome archive not official_verified",
                           "weight grid selected on October31, not independently reproduced across multiple race days",
                           "holdout already historically inspected by project, not genuinely unseen model selection",
                           "do not alter production coefficients based on 23-race single-day sensitivity alone"]}
if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
