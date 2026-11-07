"""Within-popularity 2025 outsider podium robustness and frozen proxy pick audit."""
import json,math
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"reports/outsider_top3_history_2025.json"
OUT=ROOT/"reports/outsider_top3_history_2025_robustness.md"
J=ROOT/"reports/outsider_top3_history_2025_robustness.json"

def popularity(n):
    return "4-6" if n<=6 else ("7-9" if n<=9 else "10+")
def weight(v):
    if v is None:return "unknown"
    if abs(v)<=3:return "stable_±3kg"
    if v>=10:return "gain_10+kg"
    if v<=-10:return "loss_10+kg"
    return "other_change"
def past(v):
    if v is None:return "unknown"
    return "0-3" if v<=3 else "4+"
def cell(xs):
    n=len(xs);k=sum(bool(x["finish"]<=3) for x in xs)
    return {"n":n,"top3":k,"rate":k/n if n else None}

def main():
    data=json.loads(SRC.read_text())
    races=data["races"]
    if len(races)!=351:raise ValueError("unexpected frozen 2025 sample")
    horse=[h for r in races for h in r["runners"] if h["popularity_final"]>=4]
    strat={}
    for key,fn in (("bodyweight",lambda h:weight(h["weight_delta"])),
                   ("prior_starts",lambda h:past(h["history_starts"]))):
        group={}
        for band in ("4-6","7-9","10+"):
            group[band]={}
            sample=[h for h in horse if popularity(h["popularity_final"])==band]
            for label in sorted(set(fn(h) for h in sample)):
                group[band][label]=cell([h for h in sample if fn(h)==label])
        strat[key]=group
    candidates=[]
    for r in races:
        outside=[h for h in r["runners"] if h["popularity_final"]>=4]
        if not outside:continue
        fourth=next(h for h in outside if h["popularity_final"]==4)
        frozen_number=r["preoff_candidate_top_outsider"]
        proxy=next((h for h in outside if h["number"]==frozen_number),None)
        if proxy is None:continue
        if any(h["preoff_candidate_p1"] is None for h in outside):continue
        candidates.append({"race_id":r["race_id"],"market_fourth_top3":fourth["finish"]<=3,
                           "market_fourth_third":fourth["finish"]==3,
                           "proxy_top3":proxy["finish"]<=3,
                           "proxy_third":proxy["finish"]==3,
                           "same_pick":fourth["number"]==proxy["number"],
                           "proxy_popularity":proxy["popularity_final"]})
    result={
        "source":"reports/outsider_top3_history_2025.json",
        "interpretation":"All subgroup comparisons observational; frozen proxy p1 was not calibrated for 3rd place",
        "stratified":strat,
        "selection":{
          "n":len(candidates),
          "market_4th_top3":sum(x["market_fourth_top3"] for x in candidates),
          "market_4th_third":sum(x["market_fourth_third"] for x in candidates),
          "frozen_proxy_top3":sum(x["proxy_top3"] for x in candidates),
          "frozen_proxy_third":sum(x["proxy_third"] for x in candidates),
          "same_pick":sum(x["same_pick"] for x in candidates),
          "proxy_only_top3":sum(x["proxy_top3"] and not x["market_fourth_top3"] for x in candidates),
          "pop4_only_top3":sum(x["market_fourth_top3"] and not x["proxy_top3"] for x in candidates),
        }
    }
    J.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    p=lambda c:"—" if c["rate"] is None else f"{c['top3']}/{c['n']} ({c['rate']:.1%})"
    lines=["# 2025年穴馬3着以内：同じ人気帯で条件をそろえた頑健性分析","",
           "主分析：351レース・4番人気以下3,609頭。人気帯を統一して比較することで人気別構成の影響を軽減（馬齢・距離等の交絡は残る）。",
           "**事後の馬体重やオッズは当時の情報として保存されていない場合、将来への情報漏洩に注意。**",""]
    for key,group in strat.items():
        lines+=["## "+key,"","|人気帯|条件|3着以内（件数・割合）|","|---|---|---:|"]
        for band,v in group.items():
            for label,c in v.items():
                lines.append(f"|{band}|{label}|{p(c)}|")
        lines.append("")
    s=result["selection"]
    lines+=["## 保存済み研究用p1が示す穴候補と人気4位の比較","",
      f"同一{len(candidates)}R：保存済み研究用p1最上位の4番人気以下は3着以内 {s['frozen_proxy_top3']}/{s['n']}、"
      f"市場4番人気は {s['market_4th_top3']}/{s['n']}。",
      f"ちょうど3着：研究用p1候補 {s['frozen_proxy_third']}/{s['n']}、市場4番人気 {s['market_fourth_third']}/{s['n']}。",
      f"同じ馬の選択 {s['same_pick']}/{s['n']}、研究用のみ3着内 {s['proxy_only_top3']}、4番人気のみ3着内 {s['pop4_only_top3']}。",
      "**これはv50のp3モデル比較ではない。旧モデルのp1で3着穴を拾えるという証明にはならない。**","",
      "## 結論","",
      "- 出走頭数と人気帯の影響を踏まえて、単なる『穴馬が入る』頻度と『候補1頭を選ぶ精度』を別々に評価する。",
      "- 人気4〜6番人気を3着穴候補の主分析帯とし、7〜9と10+も除外せずp3確率で順位付けする。",
      "- 事後の最終コーナー位置の優位性は、レース前の位置予測モデルがない限り採用不可。",
      "- 直前手動オッズで4位以下を抽出し、v50 p3・p2・上位3着確率・市場確率差を併記。条件別係数を学習するのは独立日程の評価後。",
      ""]
    OUT.write_text("\n".join(lines)+"\n")
    print(json.dumps(result["selection"],ensure_ascii=False))
if __name__=="__main__":main()
