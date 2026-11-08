"""Broad historical upsets: winner >=10th favorite AND >=2 podium horses >=7th.
Strictly secondary to Tokyo11-style all-three-7+-favorite event. No features
from final market or finish are used in predictors, and no promotion is allowed.
"""
from __future__ import annotations
import json,math
from pathlib import Path
from scripts.study_v50_rare_upsets_2025 import features, condition, define_extended
ROOT=Path(__file__).resolve().parents[1]
H=ROOT/"reports/outsider_top3_history_2025.json"
P=ROOT/"keiba_v48/reports/completion/paired_predictions_lag7.json"
JSON=ROOT/"reports/v50_extended_upset_gate_2025.json"
MD=ROOT/"reports/v50_extended_upset_gate_2025.md"

def measured(records,rule):
    selected=[r for r in records if condition(r,rule)]
    total=sum(r["target"] for r in records);hits=sum(r["target"] for r in selected)
    return {"n":len(records),"events":total,"flagged":len(selected),"hits":hits,
       "flag_fraction":len(selected)/len(records),
       "precision":hits/len(selected) if selected else 0,
       "recall":hits/total if total else None,
       "lift":(hits/len(selected))/(total/len(records)) if selected and total else None}

def main():
    history=json.loads(H.read_text());archive={x["race_id"]:x for x in json.loads(P.read_text())}
    rows=[]
    for x in history["races"]:
        y=archive.get(x["race_id"])
        if y is None:continue
        try:f=features(y["candidate"],y["history_starts"],len(y["horse_numbers"]))
        except Exception:continue
        rows.append({"date":x["date"],"race":x["race_id"],
          "features":f,"target":define_extended(x["top3_popularity"])})
    rows.sort(key=lambda x:(x["date"],x["race"]))
    if len(rows)!=351:raise ValueError("required 351 matched races")
    days=sorted({r["date"] for r in rows})
    cut=days[int(len(days)*.70)-1]
    train=[r for r in rows if r["date"]<=cut];hold=[r for r in rows if r["date"]>cut]
    rules=[{"min_field":f,"max_top1":p,"max_gap":g,"min_entropy":e}
      for f in (10,12,14,16) for p in (.12,.16,.20,.25,.30)
      for g in (.01,.02,.04,.08) for e in (.85,.9,.95)]
    choices=[]
    for rule in rules:
        m=measured(train,rule)
        if m["flagged"]>=12 and m["flag_fraction"]<=.2 and m["hits"]>=3 and m["lift"]>=1.5:
            choices.append((m["precision"],m["recall"],-m["flag_fraction"],rule,m))
    choices.sort(key=lambda x:(x[0],x[1],x[2]),reverse=True)
    selected=choices[0][3] if choices else None
    test=measured(hold,selected) if selected else None
    ptrain=measured(train,selected) if selected else None
    passes=bool(selected and test["events"]>=3 and test["hits"]>=2 and
      test["flag_fraction"]<=.2 and test["lift"] is not None and test["lift"]>=1.5)
    result={"event":"10th-favorite-or-worse winner and 2-plus 7th-favorite-or-worse podium",
      "n":len(rows),"events":sum(x["target"] for x in rows),
      "train":{"n":len(train),"events":sum(x["target"] for x in train),"last_date":cut},
      "holdout":{"n":len(hold),"events":sum(x["target"] for x in hold),"first_date":hold[0]["date"]},
      "selected":selected,"train_metrics":ptrain,"holdout_metrics":test,
      "sufficient_to_activate_shadow":passes,
      "production_enabled":False,
      "reason":"Old historical probabilities differ from v50 and selected historical cohort is limited.",
      "no_postrace_input":True}
    JSON.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    L=["# 2025年・広義の大波乱に限定した条件の検証","",
       "定義：10番人気以下勝利＋7番人気以下2頭以上入着。",
       f"351R中{result['events']}R（{result['events']/len(rows):.2%}）。",
       f"学習：{len(train)}R、事象{result['train']['events']}R。",
       f"未学習日：{len(hold)}R、事象{result['holdout']['events']}R。",
       f"事前の支持集中度（旧モデル）、上位2頭差、頭数、エントロピーからの候補：{selected}。",
       f"学習実績：{ptrain}。",
       f"未学習日検証：{test}。",
       f"独立検証の必要水準を通過：{passes}。",
       "**通過しても旧モデルとv50の特徴量が同一でないため本番補正は有効化しない。**",
       "重要：結果の人気は教師ラベル専用。事前の人気変数として扱わない。",""]
    MD.write_text("\n".join(L)+"\n")
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
