"""Chronological v50 research repair: two independent saved preoff distributions,
past-start-count smoothing, PL p2/p3 recalculation, official winner and podium.

This is NOT the canonical database-backed v50 implementation: historical frozen
candidate/previous are unrelated historical source probabilities and the data
cannot substitute race-quality/jockey/pace features. All 2025 outputs shadow.
No final popularity is used in features or training scores.
"""
from __future__ import annotations
import json,math,hashlib
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FROZEN=ROOT/"keiba_v48/reports/completion/paired_predictions_lag7.json"
RESULT=ROOT/"reports/outsider_top3_history_2025.json"
UPSET=ROOT/"reports/v50_rare_upset_gate_2025.json"
OUT=ROOT/"reports/v50_walkforward_rank_repair_2025.json"
MD=ROOT/"reports/v50_walkforward_rank_repair_2025.md"

def weight_prob(r,prior_weight=0.,starts_beta=0.,temperature=1.):
    p=r["candidate"];prior=r["previous"];starts=r["history_starts"]
    n=len(p)
    if len(prior)!=n or len(starts)!=n or not all(math.isfinite(v) and v>0 for v in p+prior):
        raise ValueError("invalid frozen predictors")
    # Earlier model and candidate were archived as pre-race estimates.
    # Starts is career info from frozen history, no result or odds leakage.
    mean=sum(math.log1p(s) for s in starts)/n
    logits=[((1-prior_weight)*math.log(p[i])+prior_weight*math.log(prior[i]))/temperature
      +starts_beta*(math.log1p(starts[i])-mean) for i in range(n)]
    offset=max(logits)
    es=[math.exp(l-offset) for l in logits];total=sum(es)
    return [e/total for e in es]

def pl_marginals(prob):
    n=len(prob)
    p2=[0.]*n;p3=[0.]*n
    for i in range(n):
        wi=prob[i];remaining=1-wi
        if remaining<=0:raise ValueError("degenerate winning probability")
        for j in range(n):
            if i==j:continue
            wij=wi*prob[j]/remaining
            p2[j]+=wij
            remainder=remaining-prob[j]
            if remainder<=0:raise ValueError("degenerate PL ranking")
            for k in range(n):
                if i!=k and j!=k:p3[k]+=wij*prob[k]/remainder
    for values in (prob,p2,p3):
        if abs(sum(values)-1)>1e-6:raise ValueError("marginals not normalized")
    return p2,p3

def per_race(r,truth,p,with_marginals=True):
    nums=[str(n) for n in r["horse_numbers"]]
    actual=[str(n) for n in truth["top3_numbers"]]
    if set(nums)!={str(h["number"]) for h in truth["runners"]}:
        raise ValueError("roster mismatch")
    order=sorted(range(len(nums)),key=lambda i:(-p[i],nums[i]))
    idx={n:i for i,n in enumerate(nums)}
    winner=actual[0];place2=actual[1];place3=actual[2]
    found=[nums[i] for i in order]
    top1=found[0]==winner
    first3=winner in found[:3]
    unordered=set(actual)==set(found[:3])
    ll=-math.log(max(p[idx[winner]],1e-12))
    brier=sum((p[i]-(nums[i]==winner))**2 for i in range(len(nums)))
    rec={"winner_top1":int(top1),"winner_top3":int(first3),"three_set":int(unordered),
         "winner_ll":ll,"winner_brier":brier,
         "winner_rank":found.index(winner)+1}
    if with_marginals:
        second,third=pl_marginals(p)
        rec.update({"place2_ll":-math.log(max(second[idx[place2]],1e-12)),
                    "place3_ll":-math.log(max(third[idx[place3]],1e-12)),
                    "place3_brier":sum((third[i]-(nums[i]==place3))**2 for i in range(len(nums))),
                    "place3_rank":sorted(range(len(nums)),key=lambda i:(-third[i],nums[i])).index(idx[place3])+1})
    return rec

def evaluate(records,args,with_marginals=True):
    cache=[per_race(src,result,weight_prob(src,*args),with_marginals) for src,result in records]
    n=len(cache)
    keys=cache[0]
    vals={key:sum(r[key] for r in cache) for key in keys if key!="winner_rank" and key!="place3_rank"}
    vals.update({key:round(v/n,6) for key,v in vals.items() if key.endswith("_ll") or key.endswith("_brier")})
    return {"n":n,**vals,
       "winner_top1_rate":sum(r["winner_top1"] for r in cache)/n,
       "winner_top3_rate":sum(r["winner_top3"] for r in cache)/n,
       "three_set_rate":sum(r["three_set"] for r in cache)/n}
def main():
    allhist=json.loads(RESULT.read_text())
    ids=json.loads(FROZEN.read_text())
    byid={x["race_id"]:x for x in ids}
    pairs=[]
    for r in allhist["races"]:
        base=byid.get(r["race_id"])
        if not base:continue
        if len(base.get("candidate",[]))!=len(base["horse_numbers"]):continue
        pairs.append((base,r))
    pairs.sort(key=lambda x:(x[1]["date"],x[1]["race_id"]))
    if len(pairs)!=351:raise ValueError("expected strictly matched 351")
    days=sorted({r["date"] for _,r in pairs})
    cut=days[max(0,int(len(days)*.70)-1)]
    train=[p for p in pairs if p[1]["date"]<=cut]
    test=[p for p in pairs if p[1]["date"]>cut]
    baseline=(0.,0.,1.)
    grid=[(w,b,t) for w in (0.,.25,.5,.75,1.)
          for b in (-.2,0.,.2) for t in (.85,1.,1.2)]
    trained=[]
    for args in grid:
        v=evaluate(train,args,False)
        trained.append({"prior_weight":args[0],"starts_beta":args[1],
             "temperature":args[2],"train":v})
    # Rank objectives prioritized: 1st actual selection, then top-three winner
    # capture, then probability logloss. Do not tune to heldout race outcomes.
    selected=max(trained,key=lambda q:(q["train"]["winner_top1"],
          q["train"]["winner_top3"],-q["train"]["winner_ll"]))
    choice=(selected["prior_weight"],selected["starts_beta"],selected["temperature"])
    train_base=evaluate(train,baseline);test_base=evaluate(test,baseline)
    train_choice=evaluate(train,choice);test_choice=evaluate(test,choice)
    # No claim of superiority from test unless both rank and proper scores
    # are not degraded on truly untouched future dates.
    holdout_pass=(test_choice["winner_top1"]>test_base["winner_top1"]
      and test_choice["winner_top3"]>=test_base["winner_top3"]
      and test_choice["winner_ll"]<=test_base["winner_ll"]
      and test_choice["place3_ll"]<=test_base["place3_ll"])
    outcome={"schema":"v50-historical-preoff-proxy-rank-repair-v1",
       "data":"2025 actual 1-3 results and frozen historical two-probability and starts sources",
       "prediction_data_source":str(FROZEN.relative_to(ROOT)),
       "result_data_source":str(RESULT.relative_to(ROOT)),
       "train":{"last_date":train[-1][1]["date"],"count":len(train)},
       "holdout":{"first_date":test[0][1]["date"],"count":len(test)},
       "selection_objective":"maximize win hit, then winner top3, then win logloss on train only",
       "selected":{"prior_weight":choice[0],"starts_beta":choice[1],"temperature":choice[2]},
       "comparison":{"train_base":train_base,"train_selected":train_choice,
                     "holdout_base":test_base,"holdout_selected":test_choice},
       "improvement_passes_holdout":holdout_pass,
       "promotion":"NEVER_AUTOMATIC; canonical v50 version unchanged",
       "limitations":["Historical candidate/previous distribution not identical to future canonical v50.",
          "2025 race cohort selected; timestamp proof for historic candidate source limited.",
          "Features available are archived probabilities and prior starts, not race quality or jockey residual.",
          "3rd place PL probability only approximation; no independent direct trained p3 classifier.",
          "No training on final popularity or later odds; rank3 learned only indirectly."]}
    OUT.write_text(json.dumps(outcome,ensure_ascii=False,indent=2)+"\n")
    p=lambda q:f"{q['winner_top1']}/{q['n']} ({q['winner_top1_rate']:.1%})"
    lines=["# v50順位・2/3着確率の2025年時系列改善実験","",
      f"同一351レース：学習{len(train)}R（{train[-1][1]['date']}まで）、検証{len(test)}R（{test[0][1]['date']}から）。",
      "2025年の旧モデルの事前配列を使った研究実験であり、正式v50を直接再学習した結果ではない。","",
      f"学習のみで選択した候補係数：{outcome['selected']}。","",
      "|集合|方式|本命的中|勝ち馬上位3|3頭一致|勝率LogLoss|2着LogLoss|3着LogLoss|",
      "|---|---|---:|---:|---:|---:|---:|---:|"]
    for cohort in ("train","holdout"):
        for name in ("base","selected"):
            s=outcome["comparison"][cohort+"_"+name]
            lines.append(f"|{cohort}|{name}|{p(s)}|{s['winner_top3']}/{s['n']}|"
             f"{s['three_set']}/{s['n']}|{s['winner_ll']:.3f}|{s['place2_ll']:.3f}|{s['place3_ll']:.3f}|")
    lines+=["",f"厳格な独立検証ゲート：**{'PASS' if holdout_pass else 'FAIL'}**。","",
       "検証日を見て係数を再調整しない。競馬場/騎手/馬場/当日直前オッズの項目は未学習。","",
       "本番v50本体は変更しない。",""]
    MD.write_text("\n".join(lines)+"\n")
    print(json.dumps({"selected":outcome["selected"],
        "train_n":len(train),"holdout_n":len(test),
        "holdout_base":test_base,"holdout_selected":test_choice,
        "passed":holdout_pass},ensure_ascii=False))
if __name__=="__main__":main()
