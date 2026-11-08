"""Live one-race reforecast: Tokyo 12R 2026-11-08.

Fetch the latest posted JRA win odds; fail closed if off, incomplete or mismatched.
Keep immutable timestamped captures. Recompute A-D order marginals and tickets.
"""
import datetime as dt
import hashlib,json,math
from pathlib import Path
from scripts.update_v50_20261108_live_market import fetch,geturls,DAY,JST,INPUT
from scripts.jockey_overlay_ticket_math import calculate_model

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/"operations/predictions/2026-11-08/v50_live_odds_full_tickets_1051.json"
DEST=ROOT/"operations/predictions/2026-11-08/tokyo12_live_rolling_1513.json"
REPORT=ROOT/"operations/predictions/2026-11-08/tokyo12_live_rolling_1513.md"
def main():
    source=INPUT.read_bytes()
    stored=json.loads(source)
    row=next(x for x in stored["races"] if x["date"]==DAY and x["race"]=="東京12R")
    url=geturls("東京")[12]
    fresh=fetch((row,url))
    if fresh["status"]!="preoff_odds_blended":
        raise RuntimeError("JRA fresh odds unavailable, not substituting morning odds: "+repr(fresh))
    old=json.loads(OLD.read_text())
    baseline=next(x for x in old["races"] if x["race"]=="東京12R")
    if baseline["status"]!="odds_adjusted_all_marginals":raise ValueError("old baseline invalid")
    odds={h["number"]:h for h in fresh["horses"]}
    out={}
    for label in "ABCD":
        blend=fresh["blended"][label]["ranking"]
        probs={h["number"]:h["blend_p1"] for h in blend}
        horses=[{"number":h["number"],"name":h["name"]} for h in fresh["horses"]]
        model=calculate_model(horses,[probs[h["number"]] for h in horses])
        if any(abs(sum(h[key] for h in model["horses"])-1)>1e-7 for key in ("p1","p2","p3")):raise ValueError("bad mass")
        outsider=[{**h,"popularity":odds[h["number"]]["displayed_popularity"],
                    "odds":odds[h["number"]]["odds"]}
                  for h in model["horses"] if odds[h["number"]]["displayed_popularity"]>=4]
        outsider.sort(key=lambda h:(-h["p3"],h["number"]))
        model["outsider_third_candidates"]=outsider
        out[label]=model
    now=dt.datetime.now(JST)
    result={"date":DAY,"race":"東京12R","status":"preoff_latest_odds_model_recomputed",
            "observed_at":fresh["observed_at"],"written_at":now.isoformat(),
            "off_at":fresh["off_at"],"source_url":fresh["official_url"],
            "official_sha256":fresh["official_sha256"],
            "model_input_sha256":hashlib.sha256(source).hexdigest(),
            "morning_source_sha256":hashlib.sha256(OLD.read_bytes()).hexdigest(),
            "method":"80% original ABCD win probability + 20% normalized latest live JRA odds log-geometric blend; PL recalculated",
            "no_live_bodyweight_adjustment":True,"no_live_track_bias_adjustment":True,
            "research_probabilities_not_independently_calibrated":True,
            "odds":fresh["horses"],"models":out}
    DEST.parent.mkdir(parents=True,exist_ok=True)
    if DEST.exists():raise FileExistsError("immutable snapshot already exists")
    DEST.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    old_c=baseline["models"]["C"]
    c=out["C"]
    lines=["# 11月8日 東京12R｜v50オッズ・ローリング更新","",
        "**取得 "+fresh["observed_at"]+"／発走予定 "+fresh["off_at"]+"**","",
        "**研究用推定値（校正未済）。今回の変更は単勝オッズの20%混合。馬体重・当日馬場は未補正。**","",
        "## 本命・4モデル比較","",
        "|モデル|10:51本命／1着確率|今回本命／1着確率|","|---|---|---|"]
    for label in "ABCD":
        previous=baseline["models"][label]["horses"][0]
        curr=out[label]["horses"][0]
        lines.append(f"|{label}|{previous['number']} {previous['name']} {previous['p1']:.2%}|"
                     f"{curr['number']} {curr['name']} {curr['p1']:.2%}|")
    lines+=["","## モデルC 全頭の着順別確率と最新オッズ","",
       "|モデル順位|馬番|馬名|人気|単勝|1着|2着|3着|3着以内|",
       "|---:|---:|---|---:|---:|---:|---:|---:|---:|"]
    for ix,h in enumerate(c["horses"],1):
        z=odds[h["number"]]
        lines.append(f"|{ix}|{h['number']}|{h['name']}|{z['displayed_popularity']}|{z['odds']:.1f}|"
                     f"{h['p1']:.2%}|{h['p2']:.2%}|{h['p3']:.2%}|"
                     f"{h['p1']+h['p2']+h['p3']:.2%}|")
    lines+=["","## 4番人気以下・3着穴候補（モデルC・最新p3順）","",
       "|馬番|馬名|人気|最新オッズ|3着確率|3着以内|",
       "|---:|---|---:|---:|---:|---:|"]
    for h in c["outsider_third_candidates"][:6]:
        lines.append(f"|{h['number']}|{h['name']}|{h['popularity']}|{h['odds']:.1f}|"
                     f"{h['p3']:.2%}|{h['p1']+h['p2']+h['p3']:.2%}|")
    lines+=["","## 更新後・確率上位の買い目（研究用）",""]
    for key,title in (("single","単勝"),("quinella","馬連"),("trio","3連複")):
        tickets=c["priority"][key]["tickets"][:8]
        lines += ["### "+title,"","|買い目|モデル内確率|","|---|---:|"]
        for t in tickets:
            lines.append("|"+"–".join(str(x) for x in t["numbers"])+f"|{t['p']:.2%}|")
        lines.append("")
    lines+=["## 前回10:51からの比較","",
       "|馬番|馬名|前回単勝|今回単勝|前回C勝率|今回C勝率|差（ポイント）|",
       "|---:|---|---:|---:|---:|---:|---:|"]
    oldp={h["number"]:h for h in old_c["horses"]}
    oldodds={h["number"]:h for h in baseline["odds"]}
    for h in c["horses"]:
        n=h["number"];prev=oldp[n]
        lines.append(f"|{n}|{h['name']}|{oldodds[n]['odds']:.1f}|{odds[n]['odds']:.1f}|"
                     f"{prev['p1']:.2%}|{h['p1']:.2%}|{(h['p1']-prev['p1'])*100:+.2f}|")
    lines+=["","JRA公式出馬表・掲載オッズ："+fresh["official_url"],""]
    REPORT.write_text("\n".join(lines)+"\n")
    print(json.dumps({"observed_at":fresh["observed_at"],"off_at":fresh["off_at"],
      "A-D":[{"model":label,"leader":out[label]["horses"][0]}
             for label in "ABCD"],
      "C_outsider":c["outsider_third_candidates"][:3],
      "top_trios":c["priority"]["trio"]["tickets"][:4]},ensure_ascii=False))
if __name__=="__main__":main()
