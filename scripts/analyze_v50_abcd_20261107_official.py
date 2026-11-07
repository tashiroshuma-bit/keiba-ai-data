"""Reproducible Nov 7 2026 v50 A-D evaluation from separately verified JRA winners.

Safeguards: same 33-race denominator for A-D; separately split preoff-proof
subset; never interpret final popularity as preoff odds; no invented places.
"""
from __future__ import annotations
import hashlib, json, math
from pathlib import Path
from collections import defaultdict
ROOT=Path(__file__).resolve().parents[1]
FORECAST=ROOT/"operations/predictions/2026-11-07/v50_weekend_abcd_reconnected.json"
BASE_A=ROOT/"operations/predictions/2026-11-07/v50_weekend_research.json"
WINNERS=ROOT/"operations/results/2026-11-07/jra_official_winner_popularity_review.json"
DEST=ROOT/"operations/results/2026-11-07/v50_abcd_verified_review.json"
MARKDOWN=ROOT/"operations/results/2026-11-07/v50_abcd_verified_review.md"

def evaluate(group,label):
    n=len(group)
    if not n:return {"n":0,"wins":0,"hit_rate":None,"winner_top3":0,
                     "winner_top3_rate":None,"mean_log_loss":None,"mean_brier":None}
    hits=top3=0;logloss=brier=0.0
    for record in group:
        field=record["models"][label]["horses"]
        win=record["winner_number"]
        probs={h["number"]:h["p1"] for h in field}
        if not win in probs or len(field)!=len(probs):
            raise ValueError("unmatched winner or duplicate runner "+record["race"])
        if abs(sum(probs.values())-1)>1e-7:
            raise ValueError("probability mass mismatch "+record["race"])
        hits+=field[0]["number"]==win
        top3+=any(h["number"]==win for h in field[:3])
        logloss-=math.log(max(1e-12,probs[win]))
        brier+=sum((p-int(k==win))**2 for k,p in probs.items())
    return {"n":n,"wins":hits,"hit_rate":hits/n,
            "winner_top3":top3,"winner_top3_rate":top3/n,
            "mean_log_loss":logloss/n,"mean_brier":brier/n}

def exact_mcnemar(group,a,b):
    x=y=0
    for r in group:
        hit_a=r["models"][a]["horses"][0]["number"]==r["winner_number"]
        hit_b=r["models"][b]["horses"][0]["number"]==r["winner_number"]
        if hit_a and not hit_b:x+=1
        if hit_b and not hit_a:y+=1
    n=x+y
    p=min(1,2*sum(math.comb(n,k) for k in range(min(x,y)+1))/(2**n)) if n else 1
    return {"a_only":x,"b_only":y,"discordant":n,"two_sided_p_exact":p}

def main():
    source=FORECAST.read_bytes()
    review=json.loads(WINNERS.read_text())
    forecast=json.loads(source)
    original=json.loads(BASE_A.read_text())
    truth={r["race"]:r for r in review["races"]}
    basic={r["race"]:r for r in original["races"] if r["date"]=="2026-11-07"}
    candidates=[r for r in forecast["races"] if r["date"]=="2026-11-07"]
    if len(candidates)!=36 or len(truth)!=36:
        raise ValueError("full Saturday 36-race evidence missing")
    rows=[]
    for r in candidates:
        obs=truth[r["race"]]
        pred0=basic[r["race"]]
        models=r.get("models") if r["status"]=="abcd_reconnected" else (
            {"A":pred0["v50"]} if r["status"]=="external_rejected" else {})
        is_preoff=bool(pred0.get("preoff_at_processing"))
        if r["status"]=="abcd_reconnected" and not r.get("external_preoff_proven"):
            four_preoff=False
        else:
            four_preoff=is_preoff
        rows.append({"race":r["race"],"track":r["track"],
            "winner_number":obs["winner_number"],
            "winner_popularity_final":obs["winner_final_popularity"],
            "official_result_url":obs["official_result_url"],
            "prediction_status":r["status"],"model_a_preoff_verified":is_preoff,
            "four_model_preoff_verified":four_preoff,
            "models":models})
    paired=[r for r in rows if all(k in r["models"] for k in "ABCD")]
    if len(paired)!=33:raise ValueError("expected 33 comparable flat races")
    flat=[r for r in rows if "A" in r["models"]]
    preoff=[r for r in paired if r["four_model_preoff_verified"]]
    summary={
        "schema":"jra-20261107-v50-abcd-official-winner-review-v1",
        "official_winner_source_sha256":hashlib.sha256(WINNERS.read_bytes()).hexdigest(),
        "prediction_source_sha256":hashlib.sha256(source).hexdigest(),
        "interpretation":"Research model results, not independently calibrated or genuine 33 preoff forecasts",
        "postrace_popularity_policy":"final popularity used as retrospective diagnostic only",
        "all_jra_races":36,"flat_races":len(flat),"paired_abcd_races":len(paired),
        "paired_preoff_proven_races":len(preoff),
        "paired":{a:evaluate(paired,a) for a in "ABCD"},
        "preoff_confirmed_subset":{a:evaluate(preoff,a) for a in "ABCD"},
        "a_all_flat":evaluate(flat,"A"),
        "paired_by_track":{track:{a:evaluate([r for r in paired if r["track"]==track],a)
                                  for a in "ABCD"}
                           for track in ("東京","京都","福島")},
        "favorite_winner_rate_all":sum(r["winner_final_popularity"]==1 for r in rows)/36,
        "favorite_winner_rate_paired":sum(r["winner_final_popularity"]==1 for r in paired)/len(paired),
        "favorite_winners_by_track":{track:sum(r["winner_final_popularity"]==1 for r in rows if r["track"]==track)
                                      for track in ("東京","京都","福島")},
        "a_vs_c_mcnemar_paired":exact_mcnemar(paired,"A","C"),
        "winner_popularity_counts":{str(k):sum(r["winner_final_popularity"]==k for r in rows)
                                    for k in sorted({r["winner_final_popularity"] for r in rows})},
        "races":[{"race":r["race"],"winner":r["winner_number"],
                  "winner_popularity_final":r["winner_popularity_final"],
                  "official_result_url":r["official_result_url"],
                  "a_preoff":r["model_a_preoff_verified"],
                  "abcd_preoff":r["four_model_preoff_verified"],
                  "top1":{a:{"number":r["models"][a]["horses"][0]["number"],
                               "hit":r["models"][a]["horses"][0]["number"]==r["winner_number"]}
                          for a in "ABCD" if a in r["models"]}}
                  for r in rows]}
    DEST.parent.mkdir(parents=True,exist_ok=True)
    if DEST.exists():raise FileExistsError("review already exists")
    DEST.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    p=lambda x:"—" if x is None else f"{x:.1%}"
    lines=["# 11/7 JRA v50 A〜D 結果突合・原因分析","",
           "**対象は研究用の予測です。発走後に算出されたレースを含む33Rは正式な純粋事前予測成績ではありません。**",
           "結果：JRA公式ページ（レースごとのURLをJSONに保存）。最終人気は事後比較に限定。",
           f"全36R、A平地{len(flat)}R、4モデル共通{len(paired)}R、"
           f"うち発走前入力確認{len(preoff)}R。","",
           "## 同一33R比較（研究上の参考）","",
           "|モデル|1着指名|勝ち馬上位3捕捉|Log Loss|Brier|",
           "|---|---:|---:|---:|---:|"]
    for a in "ABCD":
        m=summary["paired"][a]
        lines.append(f"|{a}|{m['wins']}/{m['n']} ({p(m['hit_rate'])})|"
                     f"{m['winner_top3']}/{m['n']} ({p(m['winner_top3_rate'])})|"
                     f"{m['mean_log_loss']:.3f}|{m['mean_brier']:.3f}|")
    lines+=["","## 発走前確認済みの同一レース限定","",
            "|モデル|1着指名|勝ち馬上位3捕捉|Log Loss|Brier|",
            "|---|---:|---:|---:|---:|"]
    for a in "ABCD":
        m=summary["preoff_confirmed_subset"][a]
        lines.append(f"|{a}|{m['wins']}/{m['n']} ({p(m['hit_rate'])})|"
                     f"{m['winner_top3']}/{m['n']} ({p(m['winner_top3_rate'])})|"
                     f"{m['mean_log_loss']:.3f}|{m['mean_brier']:.3f}|"
                     if m["n"] else f"|{a}|0|0|—|—|")
    lines+=["","## 開催場別の1着指名（同一レース・モデル内参考）","",
            "|競馬場|レース数|A|B|C|D|最終1番人気勝利／全12R|",
            "|---|---:|---:|---:|---:|---:|---:|"]
    for track in ("東京","京都","福島"):
        v=summary["paired_by_track"][track]
        lines.append(f"|{track}|{v['A']['n']}|"+ "|".join(f"{v[a]['wins']}/{v[a]['n']}" for a in "ABCD")
                     +f"|{summary['favorite_winners_by_track'][track]}/12|")
    mc=summary["a_vs_c_mcnemar_paired"]
    lines+=["","## 原因・検証仮説","",
        f"最終1番人気勝利 {sum(r['winner_final_popularity']==1 for r in rows)}/36R。"
        "東京では1番人気が多数勝ち、福島では人気薄勝利が多い。",
        f"Aのみ的中{mc['a_only']}、Cのみ的中{mc['b_only']}、"
        f"対応ありMcNemar両側正確p={mc['two_sided_p_exact']:.3f}。",
        "この1日だけで最適混合率を有意に確定できない。騎手補正と外部指数の寄与を分けて検証する。",
        "市場オッズは発走前にタイムスタンプ付きで保存したデータのみ将来予測に使用可能。",
        "最終人気を過去予測入力へ戻すと結果情報漏洩が生じるため禁止。",
        "歴史的な発走前オッズが確認できたレースで時系列アウトオブサンプル比較を実施する。","",
        "## 全36R 1着指名の○×","",
        "|競馬場・R|勝ち馬番（最終人気）|A|B|C|D|発走前4モデル確認|",
        "|---|---|---|---|---|---|---|"]
    for r in rows:
        cells=[]
        for a in "ABCD":
            m=r["models"].get(a)
            cells.append(("○" if m["horses"][0]["number"]==r["winner_number"] else "×")+
                         str(m["horses"][0]["number"]) if m else "—")
        lines.append("|"+ "|".join([r["race"],f"{r['winner_number']}（{r['winner_popularity_final']}人気）"]+
                    cells+["はい" if r["four_model_preoff_verified"] else "未確認"])+"|")
    MARKDOWN.write_text("\n".join(lines)+"\n")
    print(json.dumps({"paired":{k:[v["wins"],v["n"]] for k,v in summary["paired"].items()},
                      "preoff":[len(preoff),{k:v["wins"] for k,v in summary["preoff_confirmed_subset"].items()}],
                      "track":summary["favorite_winners_by_track"],
                      "mcnemar":summary["a_vs_c_mcnemar_paired"]},ensure_ascii=False))

if __name__=="__main__":main()
