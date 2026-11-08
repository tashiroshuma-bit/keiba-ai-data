"""Diagnose which JRA race shapes defeat archived preoff models, without leakage.

Two DISTINCT model populations:
* 2025 archived historical candidate (351 matched 1–3 outcomes)
* 2026-11-08 A-D research proxy C (34 official-verified flat)
Never pool performance rates from unlike predictor families. Postrace final
popularity is an OUTCOME stratum, never an early model feature.
"""
import hashlib,json,math
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HIST=ROOT/"reports/outsider_top3_history_2025.json"
FROZEN=ROOT/"keiba_v48/reports/completion/paired_predictions_lag7.json"
SUNDAY=ROOT/"operations/results/2026-11-08/v50_abcd_settlement.json"
MODEL=ROOT/"operations/predictions/2026-11-07/v50_weekend_abcd_reconnected.json"
OUTPUT=ROOT/"reports/v50_weak_race_diagnostics_20261108.json"
REPORT=ROOT/"reports/v50_weak_race_diagnostics_20261108.md"

def entropy(p):
    return -sum(x*math.log(x) for x in p if x>0)/math.log(len(p))
def shape(prob, prior=None, starts=None):
    n=len(prob)
    if n<3 or any(p<=0 for p in prob) or abs(sum(prob)-1)>1e-5:raise ValueError("invalid probability")
    ps=sorted(prob,reverse=True)
    gap=ps[0]-ps[1]
    f={"n":n,"top1":ps[0],"gap":gap,"entropy":entropy(prob),"top3_mass":sum(ps[:3])}
    if prior is not None and len(prior)==n:
        a=max(range(n),key=lambda i:prob[i]);b=max(range(n),key=lambda i:prior[i])
        f["prior_vs_candidate_top_disagreement"]=int(a!=b)
    if starts is not None and len(starts)==n:
        f["pct_history_0_1"]=sum(x<=1 for x in starts)/n
    return f
def field(n):return "少頭数≤9" if n<=9 else "中頭数10-13" if n<=13 else "多頭数≥14"
def concentration(p):return "高い≥30%" if p>=.30 else "中15-30%" if p>=.15 else "低い<15%"
def gaps(g):return "接戦<2pp" if g<.02 else "差2-6pp" if g<.06 else "差≥6pp"
def uncertainty(e):return "高分散≥0.95" if e>=.95 else "中0.85-0.95" if e>=.85 else "集中<0.85"
def low_history(h):return "新馬多≥50%" if h>=.5 else "新馬少<50%"
def comparison(r):
    n=len(r);w=sum(x["hit"] for x in r);capture=sum(x["winner_top3"] for x in r)
    brier=sum(x["top1_prob"] for x in r)/n if n else None
    return {"n":n,"hit":w,"hit_rate":w/n if n else None,
            "winner_top3":capture,"winner_top3_rate":capture/n if n else None,
            "mean_selected_p1":brier,
            "bias_selected_p1_minus_actual":brier-w/n if n else None,
            "winner_4plus":sum(x["winner_rank_model"]>=4 for x in r)}
def groups(rows,fieldname,selector):
    d=defaultdict(list)
    for r in rows:d[selector(r)].append(r)
    return {k:comparison(v) for k,v in sorted(d.items())}
def summarize(rows):
    return {
       "overall":comparison(rows),
       "field_size":groups(rows,"field_size",lambda x:field(x["shape"]["n"])),
       "max_p1":groups(rows,"max_p1",lambda x:concentration(x["shape"]["top1"])),
       "top1_top2_gap":groups(rows,"gap",lambda x:gaps(x["shape"]["gap"])),
       "entropy":groups(rows,"entropy",lambda x:uncertainty(x["shape"]["entropy"])),
       "venue":groups(rows,"venue",lambda x:x["venue"]),
       "top1_hit_vs_actual_winner_popularity":groups(rows,"winner_popularity",
         lambda x:"事後1人気勝利" if x["winner_popularity"]==1 else "事後2-3人気勝利" if x["winner_popularity"]<=3 else "事後4人気以下勝利"),
       "prior_disagreement":groups(rows,"prior_disagree",
          lambda x:"旧・新予測本命が不一致" if x["shape"].get("prior_vs_candidate_top_disagreement") else "旧・新予測本命が一致") if all("prior_vs_candidate_top_disagreement" in x["shape"] for x in rows) else None,
       "novice_share":groups(rows,"novice",
          lambda x:low_history(x["shape"]["pct_history_0_1"])) if all("pct_history_0_1" in x["shape"] for x in rows) else None,
    }

def main():
    hs=json.loads(HIST.read_text())
    idx={r["race_id"]:r for r in json.loads(FROZEN.read_text())}
    past=[]
    for r in hs["races"]:
        base=idx.get(r["race_id"])
        if base is None:continue
        nums=[str(n) for n in base["horse_numbers"]]
        if {str(h["number"]) for h in r["runners"]}!=set(nums):continue
        ranks=sorted(range(len(nums)),key=lambda k:(-base["candidate"][k],nums[k]))
        winner=str(r["top3_numbers"][0])
        order=[nums[k] for k in ranks]
        past.append({"date":r["date"],"race":r["race_id"],"venue":r["venue"],
          "winner":winner,"hit":int(order[0]==winner),
          "winner_top3":int(winner in order[:3]),
          "winner_rank_model":order.index(winner)+1,
          "winner_popularity":r["top3_popularity"][0],
          "top1_prob":base["candidate"][ranks[0]],
          "shape":shape(base["candidate"],base.get("previous"),base.get("history_starts"))})
    past.sort(key=lambda x:(x["date"],x["race"]))
    if len(past)!=351:raise ValueError("unreconciled historical")
    dates=sorted({r["date"] for r in past})
    cut=dates[int(len(dates)*.7)-1]
    before=[r for r in past if r["date"]<=cut]
    after=[r for r in past if r["date"]>cut]
    orig=json.loads(MODEL.read_text())
    predictions={r["race"]:r for r in orig["races"] if r["date"]=="2026-11-08" and r["status"]=="abcd_reconnected"}
    official=json.loads(SUNDAY.read_text())
    sunday=[]
    for r in official["races"]:
        if r["status"]!="evaluated":continue
        pred=predictions[r["race"]]
        hs=pred["models"]["C"]["horses"]
        nums=[str(h["number"]) for h in hs]
        winner=str(r["winner"])
        if len(nums)<3 or len(nums)!=len(set(nums)) or winner not in nums:
            raise ValueError("bad model field")
        p=[h["p1"] for h in hs]
        # All-C already sorted.
        sunday.append({"date":"2026-11-08","race":r["race"],"venue":r["track"],
           "winner":winner,"hit":int(nums[0]==winner),
           "winner_top3":int(winner in nums[:3]),
           "winner_rank_model":nums.index(winner)+1,
           "winner_popularity":r["final_popularity"][0],
           "top1_prob":p[0],"shape":shape(p)})
    if len(sunday)!=34:raise ValueError("Nov8 must have 34 matched flat races")
    combined={"schema":"v50-race-shape-diagnostics-v1","2025_train":summarize(before),
       "2025_holdout":summarize(after),"2026_11_08_research_C":summarize(sunday),
       "2025_split":{"train_n":len(before),"train_last_date":cut,"holdout_n":len(after)},
       "caveats":["2025 archived candidate is not the same as canonical v50 or Nov8 research C.",
           "2026 Nov8 is 1 day and cannot prove venue/class risk.",
           "Winner popularity is a postrace label only; cannot trigger prereace difficulty regime.",
           "Scores from two families must not be pooled or used to infer impact of causal factors.",
           "Race shape risk is observational, not a fully trained discriminative classifier."],
       "sources":[str(p.relative_to(ROOT)) for p in (HIST,FROZEN,SUNDAY,MODEL)]}
    OUTPUT.write_text(json.dumps(combined,ensure_ascii=False,indent=2)+"\n")
    lines=["# v50系モデルの苦手レース｜2025年351R＋2026年11月8日34Rの条件別比較","",
      "**2025旧研究モデルと2026年v50 A–D研究Cは別モデル。的中率を混合しない。**",
      f"2025年は開催日で学習側{len(before)}R・未使用期間{len(after)}Rに分割。","",
      "発走前に使える条件：頭数、本命確率、モデル本命と2位との差、予測分布のエントロピー、過去走数。",
      "事後確認専用：実際の勝馬の最終人気。",""]
    for name,key in (("2025前半研究モデル","2025_train"),("2025後半独立区間","2025_holdout"),("2026-11-08 C研究モデル","2026_11_08_research_C")):
        dataset=combined[key]
        overall=dataset["overall"]
        lines+=[f"## {name}","",f"全体：{overall['hit']}/{overall['n']} ({overall['hit_rate']:.1%})、勝馬上位3捕捉{overall['winner_top3']}/{overall['n']}。",""]
        for title,k in (("頭数","field_size"),("本命勝率帯","max_p1"),("1位と2位の勝率差","top1_top2_gap"),("モデルの分散","entropy"),("競馬場","venue"),("実勝馬の人気（結果説明専用）","top1_hit_vs_actual_winner_popularity"),("事前モデル間の本命一致","prior_disagreement"),("未経験馬の比率","novice_share")):
            if not dataset.get(k):continue
            lines+=["### "+title,"","|条件|件数|本命的中|勝馬上位3捕捉|予測本命p1平均|","|---|---:|---:|---:|---:|"]
            for group,s in dataset[k].items():
                lines.append(f"|{group}|{s['n']}|{s['hit']}/{s['n']} ({s['hit_rate']:.1%})|"
                  f"{s['winner_top3']}/{s['n']} ({s['winner_top3_rate']:.1%})|"
                  f"{s['mean_selected_p1']:.1%}|")
            lines.append("")
    lines+=["## 解釈のルール",""]
    lines+=["- "+c for c in combined["caveats"]]
    REPORT.write_text("\n".join(lines)+"\n")
    print(json.dumps({"historical_train":combined["2025_train"]["overall"],
      "historical_holdout":combined["2025_holdout"]["overall"],
      "2026_nov8":combined["2026_11_08_research_C"]["overall"],
      "2026_nov8_field":combined["2026_11_08_research_C"]["field_size"],
      "2026_nov8_entropy":combined["2026_11_08_research_C"]["entropy"],
      "2025_holdout_entropy":combined["2025_holdout"]["entropy"]},ensure_ascii=False))
if __name__=="__main__":main()
