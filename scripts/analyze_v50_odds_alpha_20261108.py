"""Compare v50 external A-D market weight on same 23 actual preoff snapshots.
These are already evaluated Nov8 races, so never treat optimal value as a
new training/deployment parameter. Used to diagnose why 20% weakened C top1.
"""
import math,json
from pathlib import Path
from scripts.v50_preoff_odds_blend import combine
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"operations/predictions/2026-11-08/v50_live_odds_morning_20261108.json"
MODEL=ROOT/"operations/predictions/2026-11-07/v50_weekend_abcd_reconnected.json"
ACTUAL=ROOT/"operations/results/2026-11-08/v50_abcd_settlement.json"
OUT=ROOT/"reports/v50_odds_alpha_20261108_paired.json"
MD=ROOT/"reports/v50_odds_alpha_20261108_paired.md"
ALPHAS=(0.,.05,.10,.20,.30)
def main():
    snapshots=json.loads(SOURCE.read_text())
    saved={r["race"]:r for r in json.loads(MODEL.read_text())["races"] if r["date"]=="2026-11-08"}
    official={r["race"]:r for r in json.loads(ACTUAL.read_text())["races"] if r["status"]=="evaluated"}
    rows=[r for r in snapshots["races"] if r["status"]=="preoff_odds_blended"]
    if len(rows)!=23:raise ValueError("expected 23 preoff snapshots")
    mstats={a:{m:{"n":0,"correct":0,"top3":0,"log_loss_sum":0.,
                  "brier_sum":0.,"changed_from_base":[]}
               for m in "ABCD"} for a in ALPHAS}
    for s in rows:
        race=s["race"]
        truth=official[race];win=truth["winner"]
        original=saved[race]
        odds={"phase":"preoff","source_kind":"observed_public_win_odds",
              "observed_at":s["observed_at"],"horses":s["horses"]}
        field={h["number"] for h in s["horses"]}
        for m in "ABCD":
            prior=original["models"][m]
            if field!={h["number"] for h in prior["horses"]}:raise ValueError("roster mismatch")
            base_top=prior["horses"][0]["number"]
            for a in ALPHAS:
                ret=combine(prior,odds,alpha=a,off_at=s["off_at"])
                rank=[h["number"] for h in ret["ranking"]]
                p={h["number"]:h["blend_p1"] for h in ret["ranking"]}
                r=mstats[a][m];r["n"]+=1
                r["correct"]+=rank[0]==win
                r["top3"]+=win in rank[:3]
                r["log_loss_sum"]-=math.log(p[win])
                r["brier_sum"]+=sum((value-(key==win))**2 for key,value in p.items())
                if rank[0]!=base_top:
                    r["changed_from_base"].append({"race":race,"old":base_top,"new":rank[0],
                                                    "new_wins":rank[0]==win,
                                                    "old_wins":base_top==win})
    out={"date":"2026-11-08","status":"RETROSPECTIVE_SENSITIVITY_NO_ALPHA_PROMOTION",
       "source_odds":"saved actual 10:51 full-field preoff snapshot for 23 races",
       "reference":"JRA actual winners after race, evaluation only",
       "experimental_grid":list(ALPHAS),"n":len(rows),"all_models":{},
       "no_alpha_selected":True}
    for a,models in mstats.items():
        out["all_models"][str(a)]={}
        for m,r in models.items():
            out["all_models"][str(a)][m]={
                "n":r["n"],"top1":r["correct"],"top3":r["top3"],
                "logloss":r["log_loss_sum"]/r["n"],"brier":r["brier_sum"]/r["n"],
                "changed_count":len(r["changed_from_base"]),
                "changed":r["changed_from_base"]}
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
    L=["# 2026-11-08 v50 A-D｜10:51発走前オッズ混合率の感度分析","",
       "**同じ23R。11月8日の結果を見て比較した探索分析で、最良alphaを本番昇格してはならない。**",
       "alpha=0が補正なし。alpha>0はデヴィグ後の市場確率との幾何混合。","",
       "|alpha|A本命的中|B本命的中|C本命的中|D本命的中|C勝ち馬上位3捕捉|C LogLoss|C Brier|",
       "|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for a in ALPHAS:
        q=out["all_models"][str(a)]
        L.append(f"|{a:.2f}|"+ "|".join(f"{q[m]['top1']}/23" for m in "ABCD")+
            f"|{q['C']['top3']}/23|{q['C']['logloss']:.4f}|{q['C']['brier']:.4f}|")
    L+=["","## alphaごとにCの本命が変わるレース",""]
    for a in ALPHAS:
        c=out["all_models"][str(a)]["C"]
        L.append(f"- {a:.2f}: {c['changed_count']}R　"+
                 (", ".join(f"{x['race']} {x['old']}→{x['new']} ({'改善' if x['new_wins'] else '悪化' if x['old_wins'] else '両者不的中'})"
                           for x in c["changed"]) or "変更なし"))
    L+=["","## 適用制約","",
      "2025年の市場オッズは発走後の最終値しか保存されていないため、今回の23レース結果からオッズalphaを時系列独立検証したことにはならない。",
      "改善係数はさらに別日の本物の事前オッズを保存し、同じ分母で将来検証してから選ぶ。",
      "正式v50は変更しない。",""]
    MD.write_text("\n".join(L)+"\n")
    print(json.dumps({"grid":{str(a):{m:[x["top1"],x["n"]] for m,x in out["all_models"][str(a)].items()} for a in ALPHAS}},ensure_ascii=False))
if __name__=="__main__":main()
