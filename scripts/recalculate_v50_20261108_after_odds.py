"""Recompute PL rank marginals and ticket probabilities from immutable 10:51 odds blend.
Every full-field model must normalize. Never display stale pre-market p3 as adjusted.
"""
import json,math,hashlib
from pathlib import Path
from scripts.jockey_overlay_ticket_math import calculate_model
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"operations/predictions/2026-11-08/v50_live_odds_morning_20261108.json"
OUT=ROOT/"operations/predictions/2026-11-08/v50_live_odds_full_tickets_1051.json"
MD=ROOT/"operations/predictions/2026-11-08/v50_live_odds_full_tickets_1051.md"
PREV=ROOT/"operations/predictions/2026-11-07/v50_weekend_abcd_reconnected.json"
def main():
    data=json.loads(SRC.read_text())
    prior=json.loads(PREV.read_text())
    byname={r["race"]:r for r in prior["races"] if r["date"]=="2026-11-08"}
    outputs=[]
    lines=["# 2026-11-08 v50 当日10:51 オッズ補正後・全頭順位と馬券組合せ再計算","",
           "**研究値・未校正。10:51時点の単勝オッズによる20%混合であり最終確定オッズではない。馬体重・馬場補正は未実装。**",
           "A〜D別p1/p2/p3・馬連/3連複はすべて補正後p1からPlackett–Luceで再計算。"
           "3着穴は実際のオッズ4番人気以下を対象に選ぶ。",""]
    for x in data["races"]:
        if x["status"]!="preoff_odds_blended":
            outputs.append({"race":x["race"],"status":x["status"]})
            continue
        outs={}
        market_order=sorted(x["horses"],key=lambda h:(h["displayed_popularity"],h["number"]))
        odd_by={h["number"]:h for h in x["horses"]}
        for k in "ABCD":
            ranked=x["blended"][k]["ranking"]
            p={h["number"]:h["blend_p1"] for h in ranked}
            horses=[{"number":h["number"],"name":h["name"]} for h in x["horses"]]
            probs=[p[h["number"]] for h in horses]
            calc=calculate_model(horses,probs)
            if any(abs(sum(h[t] for h in calc["horses"])-1)>1e-6 for t in ("p1","p2","p3")):
                raise ValueError("bad marginals")
            possibilities=[{**h,"preoff_popularity":odd_by[h["number"]]["displayed_popularity"],
                            "odds":odd_by[h["number"]]["odds"]}
                           for h in calc["horses"] if odd_by[h["number"]]["displayed_popularity"]>=4]
            possibilities.sort(key=lambda h:(-h["p3"],-h["p1"]-h["p2"]-h["p3"],h["number"]))
            calc["outsider_third_ranking"]=possibilities
            outs[k]=calc
        outputs.append({"race":x["race"],"status":"odds_adjusted_all_marginals",
                         "observed_at":x["observed_at"],"official_url":x["official_url"],
                         "odds":x["horses"],"models":outs})
        c=outs["C"]
        top=c["horses"][0]
        odd=odd_by[top["number"]]
        lines += [f"## {x['race']}｜C本命 {top['number']} {top['name']} 1着{top['p1']:.2%}","",
                  f"オッズ {odd['odds']:.1f}倍・当時{odd['displayed_popularity']}番人気 ／ 発走前観測{x['observed_at']}","",
                  "|C順位|馬番|馬名|市場人気|単勝|1着|2着|3着|3着以内|",
                  "|---:|---:|---|---:|---:|---:|---:|---:|---:|"]
        for i,h in enumerate(c["horses"][:8],1):
            z=odd_by[h["number"]]
            lines.append(f"|{i}|{h['number']}|{h['name']}|{z['displayed_popularity']}|"
                         f"{z['odds']:.1f}|{h['p1']:.2%}|{h['p2']:.2%}|{h['p3']:.2%}|"
                         f"{h['p1']+h['p2']+h['p3']:.2%}|")
        lines+=["",
            "3着穴（4番人気以下、更新後p3順）："+
            "、".join(f"{h['number']} {h['name']}（人気{h['preoff_popularity']}位、p3 {h['p3']:.2%}）"
                     for h in c["outsider_third_ranking"][:4]),""]
        for key,label in (("quinella","馬連"),("trio","3連複")):
            t=c["priority"][key]["tickets"][:5]
            lines+= [label+"上位組合せ："+
                     "、".join("-".join(map(str,z["numbers"]))+"（"+f"{z['p']:.2%}）" for z in t),""]
        lines.append("A/B/C/D各本命："+ "｜".join(
            f"{k} {outs[k]['horses'][0]['number']} {outs[k]['horses'][0]['p1']:.2%}" for k in "ABCD"))
        lines+=["","---",""]
    result={"schema":"jra-20261108-v50-live-full-pl-v1",
      "source_sha256":hashlib.sha256(SRC.read_bytes()).hexdigest(),
      "date":"2026-11-08","odds_time":"10:51 JST approximately",
      "research_probability_not_calibrated":True,
      "updated_count":sum(x["status"]=="odds_adjusted_all_marginals" for x in outputs),
      "races":outputs}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    MD.write_text("\n".join(lines)+"\n")
    print(json.dumps({"updated_count":result["updated_count"],
       "top":[{"race":x["race"],"horse":x["models"]["C"]["horses"][0]["name"],
                "p1":x["models"]["C"]["horses"][0]["p1"]}
               for x in outputs if x["status"]=="odds_adjusted_all_marginals"][:5]},ensure_ascii=False))
if __name__=="__main__":main()
