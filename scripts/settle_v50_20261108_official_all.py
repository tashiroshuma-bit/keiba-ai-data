"""Audit 2026-11-08 official JRA all 36 results against frozen v50 ABCD predictions.

Separation: pre-off 10:51 market shadow vs original A-D research, Tokyo12 15:14
rolling; never use result-time outcomes/features to re-predict past races.
"""
import concurrent.futures,datetime as dt,hashlib,json,math,re
from collections import Counter,defaultdict
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request,urlopen
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"operations/predictions/2026-11-07/v50_weekend_abcd_reconnected.json"
MORNING=ROOT/"operations/predictions/2026-11-08/v50_live_odds_full_tickets_1051.json"
ROLL=ROOT/"operations/predictions/2026-11-08/tokyo12_live_rolling_1513.json"
OUTPUT=ROOT/"operations/results/2026-11-08/v50_abcd_settlement.json"
REPORT=ROOT/"operations/results/2026-11-08/v50_abcd_settlement.md"
DATE="2026-11-08"
SOURCES={
 "東京":"https://sp.jra.jp/JRADB/accessS.html?CNAME=sw01sde0105202605020220261108%2F11",
 "京都":"https://sp.jra.jp/JRADB/accessS.html?CNAME=sw01sde0108202605020820261108%2F2D",
 "福島":"https://sp.jra.jp/JRADB/accessS.html?CNAME=sw01sde0103202603020320261108%2FD0",
}
def fetch(url):
    with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=18) as fh:return fh.read()
def official_urls(track):
    url=SOURCES[track];raw=fetch(url);soup=BeautifulSoup(raw,"html.parser")
    text=soup.get_text(" ",strip=True)
    if "2026年11月8日" not in text or track not in text:raise ValueError("result seed mismatch "+track)
    links={int(m[1]):urljoin(url,a["href"])
      for a in soup.select("a[href]")
      if (m:=re.fullmatch(r"(\d{1,2})R",a.get_text(" ",strip=True)))}
    # Current JRA result race does not appear in its own navigation list.
    links[{"東京":2,"京都":8,"福島":3}[track]]=url
    if len(links)!=12 or set(links)!=set(range(1,13)):
        raise ValueError("result links incomplete "+track+repr(links))
    return links

def extract(task):
    track,rno,url=task
    label=f"{track}{rno}R"
    try:
        raw=fetch(url);soup=BeautifulSoup(raw,"html.parser")
        plain=soup.get_text(" ",strip=True)
        if "2026年11月8日" not in plain or track not in plain or not re.search(rf"(?<!\d){rno}R(?!\d)",plain):
            raise ValueError("official date venue race mismatch")
        runners=[]
        for tr in soup.find_all("tr"):
            cells=[c.get_text(" ",strip=True) for c in tr.find_all(["th","td"],recursive=False)]
            if len(cells)<4 or not re.fullmatch(r"\d{1,2}",cells[0]) or not re.fullmatch(r"\d{1,2}",cells[2]):continue
            position=int(cells[0]);number=int(cells[2])
            if position>18 or number>18:continue
            m=re.search(r"(\d{1,2})番人気",cells[3])
            if not m and len(cells)>=14:
                m=re.fullmatch(r"(\d{1,2})",cells[-1])
            if not m:continue
            pop=int(m[1])
            name=re.sub(r"\d{1,2}番人気.*$","",cells[3]).strip().split(" ")[0]
            bw=None
            bw_match=re.search(r"(\d{3})kg?\s*\(([+-]?\d+)\)",cells[3])
            if bw_match:bw={"kg":int(bw_match[1]),"delta_kg":int(bw_match[2])}
            runners.append({"finish":position,"number":number,"popularity_final":pop,
                            "name":name,"bodyweight":bw})
        runners.sort(key=lambda r:r["finish"])
        if len(runners)<3 or [x["finish"] for x in runners[:3]]!=[1,2,3]:
            raise ValueError("official podium not parseable, rows:"+repr(runners[:5]))
        if len(set(x["number"] for x in runners))!=len(runners):raise ValueError("duplicated runners")
        if sorted(x["popularity_final"] for x in runners)!=list(range(1,len(runners)+1)):
            raise ValueError("final popularity ranks not complete")
        prefix=plain[:1700]
        surface="obstacle" if "障害" in prefix[:450] else ("turf" if "芝" in prefix[:450] else ("dirt" if "ダート" in prefix[:450] else "unknown"))
        goingmatch=re.search(r"(?:芝|ダート)[：:\s]*(良|稍重|重|不良)",prefix[:450])
        going=goingmatch[1] if goingmatch else None
        return {"race":label,"track":track,"race_number":rno,"status":"official_verified",
                "url":url,"sha256":hashlib.sha256(raw).hexdigest(),
                "headcount":len(runners),"surface":surface,"going":going,
                "top3_numbers":[x["number"] for x in runners[:3]],
                "top3_popularity":[x["popularity_final"] for x in runners[:3]],
                "runners":runners}
    except Exception as e:
        return {"race":label,"status":"official_unverified","url":url,
                "error":str(e)[:420]}

def evaluate(group,label,modelpath):
    n=len(group);top1=top3=exact=unordered=0;ll=brier=0.
    race_data=[]
    for race,truth,source in group:
        field=source["models"][label]["horses"]
        ranks=[h["number"] for h in field]
        winner=truth["top3_numbers"][0]
        actual=truth["top3_numbers"]
        p={h["number"]:h["p1"] for h in field}
        if set(ranks)!={h["number"] for h in truth["runners"]}:raise ValueError("model/result field mismatch "+race)
        if len(p)!=len(field) or abs(sum(p.values())-1)>1e-6:raise ValueError("invalid mass "+race)
        top1+=ranks[0]==winner;top3+=winner in ranks[:3]
        exact+=ranks[:3]==actual
        unordered+=set(ranks[:3])==set(actual)
        ll-=math.log(max(p[winner],1e-12))
        brier+=sum((v-int(k==winner))**2 for k,v in p.items())
        race_data.append({"race":race,"hit":ranks[0]==winner,"top3_capture":winner in ranks[:3],
              "winner_rank":ranks.index(winner)+1,"p1_winner":p[winner],"p1_top":field[0]["p1"]})
    return {"n":n,"top1":top1,"top1_pct":top1/n if n else None,
      "winner_in_top3":top3,"winner_in_top3_pct":top3/n if n else None,
      "exact_order_top3":exact,"unordered_top3":unordered,
      "mean_logloss":ll/n if n else None,"mean_brier":brier/n if n else None,
      "races":race_data}

def main():
    data=json.loads(BASE.read_text())
    official={}
    for track in SOURCES:
        official[track]=official_urls(track)
    tasks=[(track,i,official[track][i]) for track in SOURCES for i in range(1,13)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
        outcomes=list(pool.map(extract,tasks))
    verified={r["race"]:r for r in outcomes if r["status"]=="official_verified"}
    morning=json.loads(MORNING.read_text())
    earlier={r["race"]:r for r in morning["races"] if r["status"]=="odds_adjusted_all_marginals"}
    roll=json.loads(ROLL.read_text())
    research={r["race"]:r for r in data["races"] if r["date"]==DATE}
    assessed=[]; failures=[]
    for label,rec in research.items():
        obs=verified.get(label)
        if not obs:
            failures.append({"race":label,"reason":"no verified JRA result"});continue
        if rec["status"]!="abcd_reconnected":
            assessed.append({"race":label,"status":rec["status"],"actual":obs["top3_numbers"],
              "final_popularity":obs["top3_popularity"],"jra":obs["url"]})
            continue
        field={x["number"] for x in obs["runners"]}
        models=rec["models"]
        if any({h["number"] for h in models[m]["horses"]}!=field for m in "ABCD"):
            failures.append({"race":label,"reason":"frozen model/result runner mismatch"});continue
        hit={m:{"top":models[m]["horses"][0]["number"],
              "hit":models[m]["horses"][0]["number"]==obs["top3_numbers"][0],
              "winner_model_rank":next((i for i,h in enumerate(models[m]["horses"],1)
                 if h["number"]==obs["top3_numbers"][0]),None)} for m in "ABCD"}
        pre=earlier.get(label)
        morning_hit=None
        if pre:
            if any({h["number"] for h in pre["models"][m]["horses"]}!=field for m in "ABCD"):
                failures.append({"race":label,"reason":"10:51 runner list mismatch"});continue
            morning_hit={m:{"top":pre["models"][m]["horses"][0]["number"],
                        "hit":pre["models"][m]["horses"][0]["number"]==obs["top3_numbers"][0],
                        "winner_model_rank":next((i for i,h in enumerate(pre["models"][m]["horses"],1)
                                if h["number"]==obs["top3_numbers"][0]),None)} for m in "ABCD"}
        c=pre["models"]["C"] if pre else models["C"]
        pop_map={r["number"]:r["popularity_final"] for r in obs["runners"]}
        p3={h["number"]:h["p3"] for h in c["horses"]}
        podium=obs["top3_numbers"]
        actual_outsiders=[n for n in podium if pop_map[n]>=4]
        # candidate selector uses *preoff market ranks*, never final popularity.
        candidates=pre["models"]["C"].get("outsider_third_ranking",[]) if pre else []
        candidates=[x["number"] for x in candidates]
        cand_hits=[n for n in candidates[:3] if n in podium]
        c_full=c["horses"]
        assessed.append({"race":label,"status":"evaluated","track":rec["track"],
          "jra":obs["url"],"headcount":len(field),"going":obs["going"],
          "winner":obs["top3_numbers"][0],"podium":podium,
          "podium_names":[next((h["name"] for h in obs["runners"] if h["number"]==i),"") for i in podium],
          "final_popularity":obs["top3_popularity"],
          "model_ABCD":hit,"morning_1051_ABCD":morning_hit,
          "morning_1051_observed_at":pre["observed_at"] if pre else None,
          "C_model_source":"1051_odds" if pre else "base_research",
          "C_top5":[h["number"] for h in c_full[:5]],
          "C_podium_ordered_top3":[h["number"] for h in c_full[:3]],
          "C_p3_of_third":p3[podium[2]],
          "C_winner_rank":next(i for i,h in enumerate(c_full,1) if h["number"]==podium[0]),
          "C_predicted_top1":c_full[0]["number"],"C_top1_p1":c_full[0]["p1"],
          "C_hit":c_full[0]["number"]==podium[0],
          "C_podium_set_top3_hit":set(h["number"] for h in c_full[:3])==set(podium),
          "C_podium_top5_capture":sum(h["number"] in podium for h in c_full[:5]),
          "C_outsider_preoff_candidates_top3":candidates[:3],
          "C_outsider_preoff_top3_any_hit":bool(cand_hits),
          "C_outsider_preoff_top3_third_hit":podium[2] in candidates[:3],
          "actual_final_outsider":actual_outsiders,
          "favorite_won":obs["top3_popularity"][0]==1})
    paired=[(r["race"],verified[r["race"]],research[r["race"]]) for r in assessed if r["status"]=="evaluated"]
    prepaired=[(r["race"],verified[r["race"]],earlier[r["race"]]) for r in assessed
               if r["status"]=="evaluated" and r["race"] in earlier]
    if len(paired)<25 or len(prepaired)<15:
        raise RuntimeError("too few verified races: "+str(len(paired))+" vs "+str(len(prepaired))+" errors "+str(failures[:5]))
    base_metrics={m:evaluate(paired,m,"base") for m in "ABCD"}
    market_metrics={m:evaluate(prepaired,m,"10:51") for m in "ABCD"}
    market_base_same=[(race,obs,research[race]) for race,obs,_ in prepaired]
    paired_base_metrics={m:evaluate(market_base_same,m,"matched_base") for m in "ABCD"}
    rolltruth=verified["東京12R"]
    rollmetrics={m:evaluate([("東京12R",rolltruth,roll)],m,"15:14") for m in "ABCD"}
    rollc=roll["models"]["C"]
    rollpodium=rolltruth["top3_numbers"]
    rollouts=[x["number"] for x in rollc["outsider_third_candidates"]]
    extra={
      "rolling_1514": {"predicted_at":roll["observed_at"],
        "actual_top3":rollpodium,"final_popularity":rolltruth["top3_popularity"],
        "models":{m:{"top1":roll["models"][m]["horses"][0]["number"],
           "top1_hit":rollmetrics[m]["top1"],"winner_model_rank":rollmetrics[m]["races"][0]["winner_rank"]}
           for m in "ABCD"},
        "C_top1":rollc["horses"][0]["number"],"C_top1_p1":rollc["horses"][0]["p1"],
        "C_outsider_top3_picks":rollouts[:3],
        "C_outsider_predicted_third_hit":rollpodium[2] in rollouts[:3],
        "C_trio_top8_hit":any(set(x["numbers"])==set(rollpodium)
            for x in rollc["priority"]["trio"]["tickets"][:8]),
        "trio_actual":rollpodium}
    }
    # compare by track within same paired denominators
    bytrack={track:{m:evaluate([row for row in paired if row[0].startswith(track)],m,"base")
                      for m in "ABCD"} for track in SOURCES}
    favorite={track:Counter(r["top3_popularity"][0] for r in outcomes
       if r["status"]=="official_verified" and r["track"]==track) for track in SOURCES}
    issues={
      "c_missed_winner_rank_2":sum(r["C_winner_rank"]==2 for r in assessed if r["status"]=="evaluated" and not r["C_hit"]),
      "c_missed_winner_rank_3":sum(r["C_winner_rank"]==3 for r in assessed if r["status"]=="evaluated" and not r["C_hit"]),
      "c_missed_winner_rank_4_plus":sum(r["C_winner_rank"]>=4 for r in assessed if r["status"]=="evaluated" and not r["C_hit"]),
      "c_misses_where_favorite_won":sum(r["favorite_won"] for r in assessed if r["status"]=="evaluated" and not r["C_hit"]),
      "c_misses_where_final_outsider_won":sum(r["final_popularity"][0]>=4 for r in assessed if r["status"]=="evaluated" and not r["C_hit"]),
      "c_podium_triplet_exact":sum(r["C_podium_set_top3_hit"] for r in assessed if r["status"]=="evaluated"),
      "c_top5_podium_all3":sum(r["C_podium_top5_capture"]==3 for r in assessed if r["status"]=="evaluated"),
      "preoff_outsider_candidates_available":sum(r["morning_1051_ABCD"] is not None for r in assessed if r["status"]=="evaluated"),
      "preoff_outsider_top3_candidates_catch_third":sum(bool(r["C_outsider_preoff_top3_third_hit"]) for r in assessed if r["status"]=="evaluated" and r["morning_1051_ABCD"] is not None),
      "preoff_outsider_top3_candidates_catch_any":sum(bool(r["C_outsider_preoff_top3_any_hit"]) for r in assessed if r["status"]=="evaluated" and r["morning_1051_ABCD"] is not None),
    }
    result={"schema":"jra-2026-11-08-v50-abcd-official-results-audit-v1",
      "date":DATE,"official_verified_count":len(verified),
      "official_missing":[r for r in outcomes if r["status"]!="official_verified"],
      "paired_research_count":len(paired),
      "preoff_observed_market_count":len(prepaired),
      "results_missing_or_model_mismatch":failures,
      "base":{"metrics":base_metrics},
      "market_snapshot_1051":{"metrics":market_metrics,"base_same_races":paired_base_metrics},
      "by_track_base":bytrack,
      "favorites_by_track":{k:dict(v) for k,v in favorite.items()},
      "drivers":issues,"tokyo12":extra,
      "source_sha256":{"ABCD":hashlib.sha256(BASE.read_bytes()).hexdigest(),
                      "AM_odds":hashlib.sha256(MORNING.read_bytes()).hexdigest(),
                      "Tokyo12":hashlib.sha256(ROLL.read_bytes()).hexdigest()},
      "important_caveats":[
         "Base A-D uses research/proxy model; results are NOT canonical independently calibrated production v50.",
         "10:51 observation is actual pre-off JRA odds snapshot, not the immediate pre-start or final quote.",
         "Unmatched race fields and obstacles excluded; no horse number/name guess.",
         "Historical post-race favorite popularity is diagnostic only, not used to calculate earlier predictions.",
         "Only Tokyo12 15:14 rolling has a newer independent preserved capture.",
         "p2/p3 and quinella/trio calculated via research PL model and require independent calibration."],
      "races":assessed,"official":outcomes}
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    def p(n,d):return f"{n}/{d} ({n/d:.1%})" if d else "—"
    L=["# 2026年11月8日 JRA 全36R｜v50研究予測・オッズ補正版の結果突合","",
       "**JRA公式着順を36R取得。障害はv50平地モデル評価から除外。10:51オッズ補正は発走前取得時点だけの研究検証。**",
       f"結果取得：{len(verified)}/36、研究A-D評価{len(paired)}R、10:51オッズ補正評価{len(prepaired)}R。","",
       "## 同一レース比較：研究用ベースA-D（未校正）","",
       "|モデル|対象|本命的中|勝ち馬上位3捕捉|3頭完全一致（順不同）|Log Loss|Brier|",
       "|---|---:|---:|---:|---:|---:|---:|"]
    for m,v in base_metrics.items():
        L.append(f"|{m}|{v['n']}|{p(v['top1'],v['n'])}|{p(v['winner_in_top3'],v['n'])}|"
          f"{v['unordered_top3']}|{v['mean_logloss']:.3f}|{v['mean_brier']:.3f}|")
    L+=["","## 10:51オッズ補正の効果（同一レースの補正前後比較）","",
       "|モデル|件数|補正前1着|補正後1着|補正前Log Loss|補正後Log Loss|",
       "|---|---:|---:|---:|---:|---:|"]
    for m,v in market_metrics.items():
        b=paired_base_metrics[m]
        L.append(f"|{m}|{v['n']}|{p(b['top1'],b['n'])}|{p(v['top1'],v['n'])}|"
                 f"{b['mean_logloss']:.3f}|{v['mean_logloss']:.3f}|")
    L+=["","## ベース予測の開催場別本命的中","",
       "|競馬場|件数|A|B|C|D|最終1番人気勝利|",
       "|---|---:|---:|---:|---:|---:|---:|"]
    for track,v in bytrack.items():
        n=v["C"]["n"]
        L.append("|"+track+"|"+str(n)+"|"+
           "|".join(p(v[m]["top1"],n) for m in "ABCD")+"|"+
           str(favorite[track].get(1,0))+"/12|")
    L+=["","## 全36R｜当たり・外れ詳細","",
        "|レース|実際1-2-3着（人気）|A|B|C|D|10:51 C本命|勝ち馬C予想順位|JRA出典|",
        "|---|---|---|---|---|---|---|---:|---|"]
    for r in assessed:
        actual="/".join(f"{h}({pop}人気)" for h,pop in zip(r["actual"] if r["status"]!="evaluated" else r["podium"],r["final_popularity"]))
        if r["status"]!="evaluated":
            L.append("|"+r["race"]+"|"+actual+"|—|—|—|—|—|—|[JRA]("+r["jra"]+")|");continue
        m=[("○" if r["model_ABCD"][a]["hit"] else "×")+str(r["model_ABCD"][a]["top"]) for a in "ABCD"]
        am=r["morning_1051_ABCD"]
        mc=("○" if am["C"]["hit"] else "×")+str(am["C"]["top"]) if am else "未取得"
        L.append("|"+r["race"]+"|"+actual+"|"+"|".join(m)+"|"+mc+
                 "|"+str(r["C_winner_rank"])+"|[JRA]("+r["jra"]+")|")
    L+=["","## 具体的なミスの要因と研究仮説","",
      "- 前日保存時点のCが勝ち馬を何位にしていたか・市場で1番人気か・モデル上位5頭に入着馬がいたかを区別。",
      "- 人気薄は勝ち馬だけでなく2着・3着まで別途測定。馬場・枠順・騎手の原因断定は独立検証が必要。",
      "- 今回の分析で観察した結果・人気・馬体重を過去予測の特徴量に混ぜない。",""]
    for k,v in issues.items():L.append(f"- {k}: {v}")
    z=extra["rolling_1514"]
    L+=["","## 東京12R 15:14ローリングの正誤","",
      f"実際{z['actual_top3']}（最終人気{z['final_popularity']}）、"
      f"モデルC本命{z['C_top1']}（p1={z['C_top1_p1']:.2%}）、"
      f"本命的中={z['models']['C']['top1_hit']}、"
      f"3着穴候補上位3頭に3着馬={z['C_outsider_predicted_third_hit']}、"
      f"3連複上位8組合せ的中={z['C_trio_top8_hit']}。","",
      "## 改修候補（実データで検証するまで昇格しない）","",
      "1. 人気だけでなく市場確率とv50の差・本命人気に対する期待値・過信を検査し、時系列校正で混合率を比較。",
      "2. 勝ち馬の上位3捕捉と3着穴個別p3校正・候補1頭的中率を別の目標に設定。",
      "3. 騎手・近走状態・馬体重・馬場適性を発走前利用可能な時刻で構造化し、失敗レースで特徴量の残差検証。",
      "4. コース別・頭数別・混戦度別の係数を全日共通係数に対する追加改善で検証。",
      "5. 3連複の組合せ確率をPlackett-Luceの近似から独立データで校正し、人気4位以下の採用と資金配分を分離。",
      "6. 予測対象・データの取得時刻・再計算・結果の固定保存・自動テストを一体化し、過去情報漏洩と偶然の当たりを防ぐ。","",
      "## 方法上の注意",""]+["- "+s for s in result["important_caveats"]]
    REPORT.write_text("\n".join(L)+"\n")
    print(json.dumps({"official":len(verified),"paired":len(paired),"preoff_market":len(prepaired),
     "base":{k:[v["top1"],v["n"],v["winner_in_top3"]] for k,v in base_metrics.items()},
     "market":{k:[v["top1"],v["n"]] for k,v in market_metrics.items()},
     "market_baseline":{k:[v["top1"],v["n"]] for k,v in paired_base_metrics.items()},
     "track_C":{t:[v["C"]["top1"],v["C"]["n"]] for t,v in bytrack.items()},
     "drivers":issues,"tokyo12":z,"failures":failures},ensure_ascii=False))
if __name__=="__main__":main()
