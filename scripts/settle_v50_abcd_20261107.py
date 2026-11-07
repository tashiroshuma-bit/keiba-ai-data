"""Settle Nov 7 2026 A-D predictions versus 36 actual JRA results.

Netkeiba result-page odds are post-race *final* odds; strictly research evaluation
only. No future-available features are fed to Nov 8 preoff model.
"""
from __future__ import annotations
import concurrent.futures, datetime as dt, hashlib, json, math, re
from collections import defaultdict, Counter
from pathlib import Path
from urllib.request import Request,urlopen
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"operations/results/2026-11-07"
SOURCE=ROOT/"operations/predictions/2026-11-07/v50_weekend_abcd_reconnected.json"
PROXY=ROOT/"operations/predictions/2026-11-07/v50_weekend_research.json"
CODES={"東京":"2026050501","京都":"2026080501","福島":"2026030301"}
JST=dt.timezone(dt.timedelta(hours=9))

def fetch_result(track,race):
    url=f"https://race.netkeiba.com/race/result.html?race_id={CODES[track]}{race:02d}"
    last=None
    for _ in range(2):
        try:
            with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=17) as conn:
                raw=conn.read()
            soup=BeautifulSoup(raw,"html.parser")
            title=soup.title.get_text(" ",strip=True) if soup.title else ""
            if "2026年11月7日" not in title or f"{track}{race}R" not in title:
                raise ValueError("DATE_TRACK_RACE_TITLE_NOT_VERIFIED "+title[:130])
            table=soup.select_one("table.race_table_01")
            if not table:
                raise ValueError("RESULT_TABLE_MISSING")
            rows=[]
            for tr in table.select("tr"):
                tds=tr.find_all("td",recursive=False)
                if len(tds)<11:continue
                cells=[td.get_text(" ",strip=True) for td in tds]
                if not re.fullmatch(r"\d{1,2}",cells[0]):continue
                pos=int(cells[0])
                # Standard table: pos,frame,number,name,sex/age,weight,jockey,time,
                # margin,popularity,odds,3F,corner,trainer,bodyweight
                number=int(cells[2])
                name=cells[3].split(" ")[0]
                popularity=int(cells[9]) if cells[9].isdigit() else None
                odds=float(cells[10]) if re.fullmatch(r"\d+(?:\.\d+)?",cells[10]) else None
                rows.append({"finish":pos,"number":number,"name":name,
                             "popularity_final":popularity,"win_odds_final":odds})
            if len(rows)<3 or [h["finish"] for h in rows[:3]]!=[1,2,3]:
                raise ValueError("FINISH_ROWS_INVALID "+str(rows[:3]))
            return {"track":track,"race_number":race,"race":f"{track}{race}R",
                    "url":url,"sha256":hashlib.sha256(raw).hexdigest(),
                    "status":"verified_results","runners":rows}
        except Exception as exc:last=str(exc)
    return {"track":track,"race_number":race,"race":f"{track}{race}R",
            "url":url,"status":"result_unavailable","reason":last}

def metrics(rows,results):
    n=len(rows)
    correct_top1=winner_top3=exact3=unordered3=0
    logloss=brier=0
    crowd_match=0
    misses=[]
    for row,result in rows:
        m=row["horses"]
        winner=result["runners"][0]["number"]
        actual_top3=[h["number"] for h in result["runners"][:3]]
        p={h["number"]:h["p1"] for h in m}
        if not set(p).issubset({h["number"] for h in result["runners"]}):
            raise ValueError("PREDICTION_RUNNER_MISMATCH "+result["race"])
        first=m[0]["number"]
        correct_top1+=(first==winner)
        winner_top3+=(winner in [h["number"] for h in m[:3]])
        exact3+=([h["number"] for h in m[:3]]==actual_top3)
        unordered3+=(set(h["number"] for h in m[:3])==set(actual_top3))
        logloss-=math.log(max(1e-12,p[winner]))
        brier+=sum((v-(int(k==winner)))**2 for k,v in p.items())
        most_pop=next((h for h in result["runners"] if h["popularity_final"]==1),None)
        crowd_match+=(most_pop is not None and first==most_pop["number"])
        if first!=winner:misses.append(result["race"])
    return {"denominator":n,"top1_hit":correct_top1,
            "top1_pct":correct_top1/n if n else None,
            "winner_in_rank_top3":winner_top3,
            "winner_in_rank_top3_pct":winner_top3/n if n else None,
            "exact_order_top3":exact3,"unordered_top3":unordered3,
            "mean_logloss":logloss/n if n else None,
            "mean_multiclass_brier":brier/n if n else None,
            "same_top1_as_final_odds_favorite":crowd_match,
            "missed_races":misses}

def main():
    data=json.loads(SOURCE.read_text())
    original=json.loads(PROXY.read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        outcomes=list(pool.map(lambda t:fetch_result(*t),
                               [(track,r) for track in CODES for r in range(1,13)]))
    byresult={o["race"]:o for o in outcomes}
    full=[r for r in data["races"] if r["date"]=="2026-11-07"]
    prior={r["race"]:r for r in original["races"] if r["date"]=="2026-11-07"}
    evaluated=[];failure=[]
    for row in full:
        outcome=byresult[row["race"]]
        if outcome["status"]!="verified_results":
            failure.append({"race":row["race"],"reason":outcome.get("reason")})
            continue
        res={h["number"]:h for h in outcome["runners"]}
        winner=outcome["runners"][0]
        actual3=[h["number"] for h in outcome["runners"][:3]]
        bymodel={}
        if row["status"]=="abcd_reconnected":
            bymodel=row["models"]
        elif row["status"]=="external_rejected":
            # Original A only; do not hallucinate missing B/C/D
            bymodel={"A":prior[row["race"]]["v50"]}
        for label,model in bymodel.items():
            missing=[h["number"] for h in model["horses"] if h["number"] not in res]
            if missing:
                failure.append({"race":row["race"],"model":label,"reason":"PREDICTION_RUNNERS_NOT_IN_ACTUAL "+str(missing)})
                continue
            h=model["horses"]
            leader=h[0]
            bymodel[label]={"horses":h}
        evaluated.append({"race":row["race"],"track":row["track"],
            "race_number":row["race_number"],"prediction_status":row["status"],
            "source_quality":prior[row["race"]].get("source_quality"),
            "prediction_preoff_confirmed":prior[row["race"]].get("preoff_at_processing"),
            "result_top3":actual3,"winner_name":winner["name"],
            "winner_popularity_final":winner.get("popularity_final"),
            "winner_final_odds":winner.get("win_odds_final"),
            "models":{label:{"top1_number":model["horses"][0]["number"],
                "top1_name":model["horses"][0]["name"],
                "top1_p1":model["horses"][0]["p1"],
                "winner_prediction_rank":next((i for i,h in enumerate(model["horses"],1) if h["number"]==winner["number"]),None),
                "winner_p1":next((h["p1"] for h in model["horses"] if h["number"]==winner["number"]),None),
                "top3_numbers":[h["number"] for h in model["horses"][:3]],
                "hit_top1":model["horses"][0]["number"]==winner["number"]}
                for label,model in bymodel.items()}})
    # Paired A-D cohort for fair 4-model comparison.
    cohort=[row for row in full if row["status"]=="abcd_reconnected"
            and byresult[row["race"]]["status"]=="verified_results"
            and set(h["number"] for h in row["models"]["A"]["horses"]).issubset(
                set(h["number"] for h in byresult[row["race"]]["runners"]))]
    bymodel={label:metrics([(row["models"][label],byresult[row["race"]]) for row in cohort],outcomes)
             for label in "ABCD"}
    # Final-odds favorite is retrospective reference, NEVER input to evaluation predictions.
    favorite_hit=sum(any(h["number"]==o["runners"][0]["number"] and h["popularity_final"]==1
                         for h in o["runners"]) for o in outcomes if o["status"]=="verified_results")
    favorite_den=sum(o["status"]=="verified_results" for o in outcomes)
    result={"date":"2026-11-07",
            "schema":"jra-v50-abcd-settlement-with-final-odds-reference-v1",
            "prediction_sha256":hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            "result_source":"netkeiba race result webpages; compare representative JRA official data",
            "odds_timing":"POST_RACE_FINAL_FOR_DIAGNOSTICS_ONLY_NOT_PREOFF",
            "race_results_verified":favorite_den,"race_results_failed":failure,
            "paired_abcd_races":len(cohort),"paired_abcd_models":bymodel,
            "final_odds_favorite_wins_all_result_races":favorite_hit,
            "all_result_races":favorite_den,"evaluated":evaluated,
            "raw_results":outcomes}
    BASE.mkdir(parents=True,exist_ok=True)
    out=BASE/"v50_abcd_actual_results.json"
    if out.exists():raise FileExistsError("immutable settlement exists")
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    lines=["# 2026-11-07 v50 A〜D 全結果突合","",
           "**注意：前のv50はキャリア成績代理特徴量による研究予測。発走後の最終オッズは診断用であり事前予測には使用しない。**","",
           f"結果取得 {favorite_den}/36、4モデル同じレースを比較 {len(cohort)}R。",
           f"最終1番人気の勝利：{favorite_hit}/{favorite_den}R。","",
           "## モデル別検証｜同じレース・同じ分母","",
           "|モデル|件数|1着指名的中|勝ち馬を上位3頭に捕捉|3頭完全一致（順不同）|Log Loss|Brier|",
           "|---|---:|---:|---:|---:|---:|---:|"]
    for label,stats in bymodel.items():
        lines.append(f"|{label}|{stats['denominator']}|{stats['top1_hit']} ({stats['top1_pct']:.1%})|"
                     f"{stats['winner_in_rank_top3']} ({stats['winner_in_rank_top3_pct']:.1%})|"
                     f"{stats['unordered_top3']}|{stats['mean_logloss']:.4f}|{stats['mean_multiclass_brier']:.4f}|")
    lines+=["","## 全レース結果とモデル別1着指名","",
            "|レース|勝ち馬（最終人気）|A|B|C|D|",
            "|---|---|---|---|---|---|"]
    for x in evaluated:
        win=x["result_top3"][0]
        label=f"{win} {x['winner_name']}（{x['winner_popularity_final']}人気）"
        m=[]
        for a in "ABCD":
            v=x["models"].get(a)
            m.append(("◎" if v["hit_top1"] else "×")+str(v["top1_number"]) if v else "—")
        lines.append("|"+ "|".join([x["race"],label]+m)+"|")
    if failure:
        lines+=["","## 未突合理由","",
                "~~~json",json.dumps(failure,ensure_ascii=False,indent=2),"~~~",""]
    (BASE/"v50_abcd_actual_results_report.md").write_text("\n".join(lines)+"\n")
    print(json.dumps({"results":favorite_den,"paired":len(cohort),"metrics":bymodel,
                      "failures":failure},ensure_ascii=False))

if __name__=="__main__":main()
