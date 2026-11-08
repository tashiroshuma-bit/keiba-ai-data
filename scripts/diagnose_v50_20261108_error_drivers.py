"""Focused postmortem diagnostics of Nov 8 official results vs frozen Sunday forecasts.
Descriptive audit only; no model refit on November 8 evaluation cohort.
"""
from collections import Counter,defaultdict
from pathlib import Path
import json,math
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"operations/results/2026-11-08/v50_abcd_settlement.json"
OUT=ROOT/"operations/results/2026-11-08/v50_error_drivers_20261108.json"
MD=ROOT/"operations/results/2026-11-08/v50_error_drivers_20261108.md"

def grade_count(rows,key):
    def one(g):
        n=len(g);win=sum(r["C_hit"] for r in g)
        return {"n":n,"win":win,"hit_rate":win/n if n else None}
    blocks=defaultdict(list)
    for r in rows:blocks[key(r)].append(r)
    return {k:one(v) for k,v in sorted(blocks.items())}
def pct(x,n):return f"{x}/{n} ({x/n:.1%})" if n else "—"

def main():
    d=json.loads(SRC.read_text())
    rows=[r for r in d["races"] if r["status"]=="evaluated"]
    if len(rows)!=34:raise ValueError("expected 34 evaluated flat races")
    report={}
    report["c_by_win_popularity"]=grade_count(rows,lambda r: "1番人気" if r["final_popularity"][0]==1 else ("2-3番人気" if r["final_popularity"][0]<=3 else ("4-6番人気" if r["final_popularity"][0]<=6 else "7番人気以下")))
    report["c_by_track"]=grade_count(rows,lambda r:r["track"])
    report["c_missed_winner_rank_distribution"]=dict(sorted(Counter(
        ("1" if r["C_winner_rank"]==1 else ("2-3" if r["C_winner_rank"]<=3 else ("4-5" if r["C_winner_rank"]<=5 else "6+")))
        for r in rows).items()))
    report["C_podium_recall_top5"]={
        "zero":sum(r["C_podium_top5_capture"]==0 for r in rows),
        "one":sum(r["C_podium_top5_capture"]==1 for r in rows),
        "two":sum(r["C_podium_top5_capture"]==2 for r in rows),
        "three":sum(r["C_podium_top5_capture"]==3 for r in rows)}
    report["C_hit_races"]=[{"race":r["race"],"top1":r["C_predicted_top1"],
                            "actual":r["podium"],"popularity":r["final_popularity"],
                            "source":r["jra"]} for r in rows if r["C_hit"]]
    report["C_miss_races"]=[{"race":r["race"],"top1":r["C_predicted_top1"],"p1":r["C_top1_p1"],
                            "winner":r["winner"],"winner_rank":r["C_winner_rank"],
                            "actual":r["podium"],"popularity":r["final_popularity"],
                            "source":r["jra"]} for r in rows if not r["C_hit"]]
    markets=[r for r in rows if r["morning_1051_ABCD"] is not None]
    if len(markets)!=23:raise ValueError("expected 23 preoff observations")
    report["market_same_race_C_flip"]={
        "both_hit":[],"base_hit_only":[],"market_hit_only":[],"neither_hit":[]}
    for r in markets:
        base=r["model_ABCD"]["C"]["hit"]
        new=r["morning_1051_ABCD"]["C"]["hit"]
        tag="both_hit" if base and new else "base_hit_only" if base else "market_hit_only" if new else "neither_hit"
        report["market_same_race_C_flip"][tag].append(r["race"])
    report["market_flip_counts"]={key:len(v) for key,v in report["market_same_race_C_flip"].items()}
    report["p3_recall_23"]={
        "with_final_outsider_third":sum(r["final_popularity"][2]>=4 for r in markets),
        "candidate_top3_third_hit":sum(r["C_outsider_preoff_top3_third_hit"] for r in markets),
        "with_final_outsider_in_podium":sum(any(pop>=4 for pop in r["final_popularity"]) for r in markets),
        "candidate_top3_any_hit":sum(r["C_outsider_preoff_top3_any_hit"] for r in markets),
        "n":23}
    # Distinguish hit of actual winner from "best predicted public favorite".
    report["c_market_chosen_as_public_favorite"]=grade_count(markets,lambda r:"true_final_favorite_won" if r["favorite_won"] else "true_final_favorite_lost")
    report["c_confidence_1051"]= {
        "top1_mean_p1":sum(r["C_top1_p1"] for r in markets)/len(markets),
        "top1_hit_rate":sum(r["C_hit"] for r in markets)/len(markets),
        "note":"Individual race C_top1_p1 comes from 10:51 model when present, not a calibrated confidence band"}
    # For champion showdown on 34 races, any model hits, consensus:
    report["model_disagreement"]={
        "at_least_one_hit":sum(any(r["model_ABCD"][a]["hit"] for a in "ABCD") for r in rows),
        "all_four_hit":sum(all(r["model_ABCD"][a]["hit"] for a in "ABCD") for r in rows),
        "none_hit":sum(not any(r["model_ABCD"][a]["hit"] for a in "ABCD") for r in rows),
        "C_D_same_correct":sum(r["model_ABCD"]["C"]["hit"] and r["model_ABCD"]["D"]["hit"] for r in rows),
        "C_only_vs_D":sum(r["model_ABCD"]["C"]["hit"] and not r["model_ABCD"]["D"]["hit"] for r in rows),
        "D_only_vs_C":sum(r["model_ABCD"]["D"]["hit"] and not r["model_ABCD"]["C"]["hit"] for r in rows),
    }
    report["rolling_tokyo12"]=d["tokyo12"]["rolling_1514"]
    result={"schema":"jra-20261108-v50-c-error-structural-diagnostics-v1",
            "source":"operations/results/2026-11-08/v50_abcd_settlement.json",
            "caution":"descriptive after the fact, not an estimated causal effect",
            "denominator_base":34,"denominator_market":23,"results":report}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    lines=["# 2026年11月8日 JRA｜v50的中・不的中原因の構造化比較","",
      "研究用モデル。11月8日データで事後に最適化した新係数を正式昇格しない。発走後確定人気や結果から遡って予測しない。","",
      "## 本命的中：勝ち馬の最終人気別（Cモデル・34R）","",
      "|勝ち馬の人気帯|本命的中|","|---|---:|"]
    for name,v in report["c_by_win_popularity"].items():
        lines.append(f"|{name}|{pct(v['win'],v['n'])}|")
    lines+=["","## 本命的中：競馬場別（Cモデル・34R）","",
      "|競馬場|本命的中|","|---|---:|"]
    for name,v in report["c_by_track"].items():
        lines.append(f"|{name}|{pct(v['win'],v['n'])}|")
    lines+=["","## 勝ち馬のC予想順位別（34R）","",
       "|予想順位|レース数|","|---|---:|"]
    for name,v in report["c_missed_winner_rank_distribution"].items():
        lines.append(f"|{name}|{v}|")
    lines+=["","## 的中10R｜モデルC本命と実際の着順","",
      "|レース|予想本命番|実着順1-2-3（最終人気）|JRA|",
      "|---|---:|---|---|"]
    for r in report["C_hit_races"]:
        lines.append(f"|{r['race']}|{r['top1']}|"+"/".join(f"{n}({p}人)" for n,p in zip(r["actual"],r["popularity"]))+
                     f"|[公式]({r['source']})|")
    lines+=["","## 不的中24R｜実際の勝ち馬をどこまで捕捉したか","",
      "|レース|本命|勝ち馬|勝ち馬C順位|人気（勝ち馬）|JRA|",
      "|---|---:|---:|---:|---:|---|"]
    for r in report["C_miss_races"]:
        lines.append(f"|{r['race']}|{r['top1']}|{r['winner']}|{r['winner_rank']}|"
                     f"{r['popularity'][0]}|[公式]({r['source']})|")
    q=report["market_flip_counts"]
    lines+=["","## 10:51市場オッズ混合でC本命に何が起きたか（同一23R）","",
      f"- どちらも的中：{q['both_hit']}R",
      f"- 元モデルのみ的中：{q['base_hit_only']}R（{', '.join(report['market_same_race_C_flip']['base_hit_only'])}）",
      f"- オッズモデルのみ的中：{q['market_hit_only']}R（{', '.join(report['market_same_race_C_flip']['market_hit_only'])}）",
      f"- どちらも不的中：{q['neither_hit']}R",
      ""]
    p3=report["p3_recall_23"]
    lines+=["## 3着穴・2〜3着検証","",
      f"- 実際の3着が4番人気以下：{p3['with_final_outsider_third']}/{p3['n']}R。",
      f"- 発走前人気4位以下からCが選んだp3候補上位3頭に実際3着：{p3['candidate_top3_third_hit']}/{p3['n']}R。",
      f"- 4番人気以下がどこかで3着以内：{p3['with_final_outsider_in_podium']}/{p3['n']}R。",
      f"- 発走前人気4位以下p3候補上位3頭のいずれかが3着以内：{p3['candidate_top3_any_hit']}/{p3['n']}R。",
      "注意：3着が4番人気以下でなかったレースにはそもそも穴候補が3着を取れる可能性がない。後付け最終人気との比較は定義の差に注意。",""]
    pc=report["C_podium_recall_top5"]
    lines+=["## 上位5頭まで候補を広げたときの3頭捕捉","",
      f"実際の1〜3着3頭ともC上位5頭：{pc['three']}/34R、2頭だけ：{pc['two']}R、1頭だけ：{pc['one']}R、ゼロ：{pc['zero']}R。",
      "3連複の全組合せを考える前に、候補のカバレッジを最大化する必要あり。","",
      "## 設計上の改修優先順位（検証条件付き）","",
      "P0① **入力充足・騎手/近走/馬場**：7人気以下の好走馬をモデル上位に上げられるか時系列ホールドアウトで実証。",
      "P0② **市場補正係数のウォークフォワード最適化**：alpha 0/.05/.10/.20/.30を比較。1着指名の結果だけでなくLog Loss、Brier、穴候補捕捉を同時評価。",
      "P1③ **的中確率と市場差の分離**：本命と購入推奨を別の意思決定として表示。リターン予測ではなく順位精度が第一。",
      "P1④ **3着穴専用予測と3連複生成**：3着穴p3候補の順位改善と組合せ包絡率を別々に評価。1日間の過去結果への後付け加点は禁止。",
      "P2⑤ **馬場/競馬場別の条件モデル**：晴/良/稍重・馬場内外・脚質など事前に判定できる情報だけ使用。",
      "P2⑥ **推定分布の校正**：モデル出力の確率は研究用なので時系列・場別に信頼区間と校正曲線で検証。",
      ""]
    MD.write_text("\n".join(lines)+"\n")
    print(json.dumps({"model_disagreement":report["model_disagreement"],
     "miss_win_rank":report["c_missed_winner_rank_distribution"],
     "market_flip":report["market_same_race_C_flip"],
     "by_pop":report["c_by_win_popularity"],
     "p3":p3,"top5":pc},ensure_ascii=False))
if __name__=="__main__":main()
