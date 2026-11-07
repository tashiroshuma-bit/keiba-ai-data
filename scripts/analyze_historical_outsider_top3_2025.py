"""2025 historical JRA outsider podium analysis, using actual per-runner Yahoo results.

Historical results are postrace reference, never preoff features. Preserved
candidate score and history starts originate from frozen preoff history records.
"""
from __future__ import annotations
import concurrent.futures
import datetime as dt
import hashlib
import json
import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
PAIRED=ROOT/"keiba_v48/reports/completion/paired_predictions_lag7.json"
OUT=ROOT/"reports/outsider_top3_history_2025.json"
REPORT=ROOT/"reports/outsider_top3_history_2025.md"
PREVIOUS=ROOT/"reports/outsider_top3_20261031_1101_results.json"
MAX_WORKERS=6

def ci(n,positive):
    if not n:return None
    z=1.96;p=positive/n;d=1+z*z/n
    m=(p+z*z/(2*n))/d
    h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [max(0,m-h),min(1,m+h)]

def get(url):
    last=None
    for retry in range(2):
        try:
            with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; historical-race-review/1.0)"}),timeout=18) as fh:
                return fh.read()
        except Exception as ex:
            last=ex
            time.sleep(0.4*(retry+1))
    raise last

def extract(rec):
    rid=str(rec["race_id"])
    if not re.fullmatch(r"2025\d{8}",rid):
        raise ValueError("invalid 2025 race ID")
    url="https://sports.yahoo.co.jp/keiba/race/result/"+rid[2:]
    raw=get(url)
    soup=BeautifulSoup(raw,"html.parser")
    title=soup.title.get_text(" ",strip=True) if soup.title else ""
    if "2025年" not in title:
        raise ValueError("wrong page year: "+title[:90])
    table=None
    for t in soup.select("table"):
        tr=t.find("tr")
        if tr and "着順" in tr.get_text(" ",strip=True) and "人気" in tr.get_text(" ",strip=True):
            table=t;break
    if table is None:raise ValueError("full runner table unavailable")
    lines=[]
    for tr in table.select("tr"):
        cells=[x.get_text(" ",strip=True) for x in tr.find_all(["th","td"],recursive=False)]
        if len(cells)<9 or not re.fullmatch(r"\d{1,2}",cells[0]) or not re.fullmatch(r"\d{1,2}",cells[2]):
            continue
        rank=int(cells[0]);number=int(cells[2])
        match=re.search(r"(\d{1,2})\s*\((\d+(?:\.\d+)?)\)",cells[7])
        if not match:continue
        popularity,odds=int(match[1]),float(match[2])
        if odds<=1 or not math.isfinite(odds):continue
        weightmatch=re.search(r"/\s*\d{3}\(([+-]?\d+)\)",cells[3])
        if not weightmatch:weightmatch=re.search(r"\d{3}\(([+-]?\d+)\)",cells[3])
        weight_delta=int(weightmatch[1]) if weightmatch else None
        corners=re.findall(r"\d{1,2}",cells[5].split(" ")[0])
        final_corner=int(corners[-1]) if corners else None
        threef_match=re.search(r"(\d{2}\.\d)",cells[5])
        final3f=float(threef_match[1]) if threef_match else None
        lines.append({"finish":rank,"number":number,"popularity_final":popularity,"final_win_odds":odds,
                      "horse_name":cells[3].split(" ")[0],"weight_delta":weight_delta,
                      "final_corner_position":final_corner,"final_3f":final3f})
    lines.sort(key=lambda x:x["finish"])
    field=len(lines)
    if field<5 or field>18 or len(set(x["number"] for x in lines))!=field:
        raise ValueError("invalid finish field "+str(field))
    pops=sorted(x["popularity_final"] for x in lines)
    if pops!=list(range(1,field+1)):raise ValueError("popularity not 1..field")
    if [x["finish"] for x in lines[:3]]!=[1,2,3]:
        raise ValueError("missing unique top 3")
    if str(lines[0]["number"])!=str(rec["winner_horse_number"]):
        raise ValueError("winner mismatch to frozen historic result")
    nums=[str(x) for x in rec["horse_numbers"]]
    if set(nums)!=set(str(x["number"]) for x in lines):
        raise ValueError("runner mismatch to frozen preoff roster")
    scores=rec.get("candidate") or []
    starts=rec.get("history_starts") or []
    smap={str(n):float(v) for n,v in zip(nums,scores)} if len(scores)==len(nums) else {}
    hmap={str(n):v for n,v in zip(nums,starts)} if len(starts)==len(nums) else {}
    for horse in lines:
        horse["preoff_candidate_p1"]=smap.get(str(horse["number"]))
        horse["history_starts"]=hmap.get(str(horse["number"]))
    start=text=soup.get_text(" ",strip=True)
    beginning=text[:1100]
    surface="芝" if re.search(r"芝[・\s]",beginning) else ("ダート" if "ダート" in beginning else "不明")
    dist_match=re.search(r"(?:芝|ダート)[^\d]{0,15}(\d{3,4})m",beginning)
    dist=int(dist_match[1]) if dist_match else None
    going_match=re.search(r"馬場\s*[：:]\s*(良|稍重|重|不良)",beginning)
    going=going_match[1] if going_match else None
    venue={"01":"札幌","02":"函館","03":"福島","04":"新潟","05":"東京","06":"中山",
           "07":"中京","08":"京都","09":"阪神","10":"小倉"}.get(rid[4:6],"不明")
    amount=sum(1/x["final_win_odds"] for x in lines)
    market={x["number"]:1/x["final_win_odds"]/amount for x in lines}
    favorite=next(x for x in lines if x["popularity_final"]==1)
    runnerup=next(x for x in lines if x["popularity_final"]==2)
    favorite_share=market[favorite["number"]]
    gap=favorite_share-market[runnerup["number"]]
    outside=sorted((x for x in lines if x["popularity_final"]>=4),
                   key=lambda x:(-x["preoff_candidate_p1"] if x["preoff_candidate_p1"] is not None else 0,x["number"]))
    return {"race_id":rid,"date":rec["off_timestamp"][:10],"venue":venue,
            "surface":surface,"distance_m":dist,"going":going,
            "field_size":field,"favorite_probability_final":favorite_share,
            "favorite_gap_final":gap,"favorite_odds_final":favorite["final_win_odds"],
            "top3_popularity":[x["popularity_final"] for x in lines[:3]],
            "top3_numbers":[x["number"] for x in lines[:3]],
            "any_outsider_top3":any(x["popularity_final"]>=4 for x in lines[:3]),
            "third_outsider":lines[2]["popularity_final"]>=4,
            "second_outsider":lines[1]["popularity_final"]>=4,
            "outsider_winner":lines[0]["popularity_final"]>=4,
            "favorite_winner":lines[0]["popularity_final"]==1,
            "outsider_count_top3":sum(x["popularity_final"]>=4 for x in lines[:3]),
            "preoff_candidate_top_outsider":outside[0]["number"] if outside else None,
            "preoff_candidate_top_outsider_placed":outside[0]["finish"]<=3 if outside else None,
            "preoff_candidate_top_outsider_third":outside[0]["finish"]==3 if outside else None,
            "runners":lines,"result_url":url,"result_sha256":hashlib.sha256(raw).hexdigest()}

def safe(rec):
    try:return extract(rec)
    except Exception as e:return {"race_id":rec.get("race_id"),"error":str(e)[:180]}

def band_field(n):
    if n<=9:return "5-9頭"
    if n<=13:return "10-13頭"
    return "14-18頭"
def band_share(n):
    if n<.2:return "20%未満"
    if n<.3:return "20-30%"
    if n<.4:return "30-40%"
    return "40%以上"
def band_gap(n):
    if n<.03:return "3pp未満"
    if n<.08:return "3-8pp"
    return "8pp以上"
def band_pop(n):
    if n<=6:return "4-6番人気"
    if n<=9:return "7-9番人気"
    return "10番人気以下"
def band_weight(v):
    if v is None:return "欠損"
    if v<=-10:return "-10kg以下"
    if v<=-4:return "-9kgから-4kg"
    if v<=3:return "-3kgから+3kg"
    if v<=9:return "+4kgから+9kg"
    return "+10kg以上"
def band_starts(v):
    if v is None:return "欠損"
    if v<=1:return "0-1走"
    if v<=3:return "2-3走"
    if v<=6:return "4-6走"
    return "7走以上"

def grouped(rows,fn,event):
    groups=defaultdict(list)
    for r in rows:groups[fn(r)].append(r)
    return {k:{"n":len(v),"positive":sum(bool(event(r)) for r in v),
               "rate":sum(bool(event(r)) for r in v)/len(v),
               "wilson95":ci(len(v),sum(bool(event(r)) for r in v))}
            for k,v in sorted(groups.items())}

def main():
    source=json.loads(PAIRED.read_text())
    if len(source)<300:raise ValueError("history truncated")
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        parsed=list(pool.map(safe,source))
    rows=[r for r in parsed if "error" not in r]
    failed=[r for r in parsed if "error" in r]
    if len(rows)<100:raise RuntimeError("too few valid historical races: "+str(len(rows))+" "+str(failed[:5]))
    # Respective denominators: race level vs actual available 4th+ horses.
    horse_rows=[{"race_id":r["race_id"],"venue":r["venue"],"surface":r["surface"],
                 "field_size":r["field_size"],"favorite_probability_final":r["favorite_probability_final"],
                 **h} for r in rows for h in r["runners"] if h["popularity_final"]>=4]
    assert len(horse_rows)>=len(rows)*2
    race_features={
      "field_size":grouped(rows,lambda r:band_field(r["field_size"]),lambda r:r["any_outsider_top3"]),
      "surface":grouped(rows,lambda r:r["surface"],lambda r:r["any_outsider_top3"]),
      "venue":grouped(rows,lambda r:r["venue"],lambda r:r["any_outsider_top3"]),
      "favorite_market_share":grouped(rows,lambda r:band_share(r["favorite_probability_final"]),lambda r:r["any_outsider_top3"]),
      "favorite_vs_second_gap":grouped(rows,lambda r:band_gap(r["favorite_gap_final"]),lambda r:r["any_outsider_top3"]),
      "favorite_winner":grouped(rows,lambda r:"1番人気1着" if r["favorite_winner"] else "1番人気非勝利",lambda r:r["any_outsider_top3"]),
      "third_outsider_by_field":grouped(rows,lambda r:band_field(r["field_size"]),lambda r:r["third_outsider"]),
      "third_outsider_by_surface":grouped(rows,lambda r:r["surface"],lambda r:r["third_outsider"]),
      "third_outsider_by_share":grouped(rows,lambda r:band_share(r["favorite_probability_final"]),lambda r:r["third_outsider"]),
    }
    horse_features={
      "popularity":grouped(horse_rows,lambda h:band_pop(h["popularity_final"]),lambda h:h["finish"]<=3),
      "popularity_third":grouped(horse_rows,lambda h:band_pop(h["popularity_final"]),lambda h:h["finish"]==3),
      "bodyweight_change":grouped(horse_rows,lambda h:band_weight(h["weight_delta"]),lambda h:h["finish"]<=3),
      "history_starts":grouped(horse_rows,lambda h:band_starts(h["history_starts"]),lambda h:h["finish"]<=3),
      "surface":grouped(horse_rows,lambda h:h["surface"],lambda h:h["finish"]<=3),
      "venue":grouped(horse_rows,lambda h:h["venue"],lambda h:h["finish"]<=3),
      "finish_corner_hindsight":grouped(horse_rows,lambda h:
          "最終コーナー3番手以内" if h["final_corner_position"] is not None and h["final_corner_position"]<=3
          else ("最終コーナー4番手以下" if h["final_corner_position"] is not None else "欠損"),
          lambda h:h["finish"]<=3),
    }
    n=len(rows)
    mainstats={"n":n,"outsider_podium_races":sum(r["any_outsider_top3"] for r in rows),
               "outsider_third_races":sum(r["third_outsider"] for r in rows),
               "outsider_second_races":sum(r["second_outsider"] for r in rows),
               "outsider_win_races":sum(r["outsider_winner"] for r in rows),
               "top3_outsider_horses":sum(r["outsider_count_top3"] for r in rows),
               "avg_outsider_podium_count":sum(r["outsider_count_top3"] for r in rows)/n,
               "outsider_horse_entries":len(horse_rows),
               "outsider_horse_top3":sum(h["finish"]<=3 for h in horse_rows),
               "outsider_horse_third":sum(h["finish"]==3 for h in horse_rows),
               "candidate_outsider_top1_placed":sum(bool(r["preoff_candidate_top_outsider_placed"]) for r in rows),
               "candidate_outsider_top1_third":sum(bool(r["preoff_candidate_top_outsider_third"]) for r in rows)}
    previous=json.loads(PREVIOUS.read_text())
    report={"schema":"historical-outsider-podium-2025-v1",
       "source":"Yahoo Sports published JRA result tables, matched to preserved JRA 2025 frozen prediction winner and runner list",
       "source_history_sha256":hashlib.sha256(PAIRED.read_bytes()).hexdigest(),
       "historical_race_records":len(source),"verified_races":n,"failed_races":failed,
       "summary":mainstats,"race_features":race_features,"horse_features":horse_features,
       "previous_2026_two_day_case_study":{"n":previous["overall"]["n"],
          "outsider_podium":previous["overall"]["any_outsider_top3_count"],
          "third_outsider":previous["overall"]["third_outsider_count"]},
       "limitations":["2025 historical results were retrieved postrace; all odds and corner/3F markers are hindsight reference.",
                      "Conditional popularity4+ always increases top3 opportunity as the field grows; never interpret frequency as a calibrated forecast.",
                      "Odds popularity or course condition after results are not preoff signals.",
                      "Saved candidate is research prior, NOT v50 p3 nor standalone calibrated third-place probability.",
                      "This subset is the archived 2025 sample of 396 race IDs, not guaranteed random or full JRA season.",
                      "Horse-level observations within the same race are not statistically independent.",
                      "The 2026 42-race case study is a separate sample, not used to train scores."],
       "races":rows}
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    pct=lambda n,d:f"{n/d:.1%}" if d else "—"
    lines=["# 2025年過去データ：4番人気以下の3着以内・3着穴分析","",
           f"2025年保存済みレース：{len(source)}R、結果・全頭人気・勝ち馬照合：{n}R、除外：{len(failed)}R。","",
           "**すべて最終人気を用いた事後分析であり、将来の推定確率や因果効果ではない。**","",
           f"- 4番人気以下が1頭以上3着以内：{mainstats['outsider_podium_races']}/{n} ({pct(mainstats['outsider_podium_races'],n)})",
           f"- 3着が4番人気以下：{mainstats['outsider_third_races']}/{n} ({pct(mainstats['outsider_third_races'],n)})",
           f"- 4番人気以下の全出走 {len(horse_rows)}頭・入着 {mainstats['outsider_horse_top3']}頭 ({pct(mainstats['outsider_horse_top3'],len(horse_rows))})",
           f"- 過去の研究用モデルp1で4番人気以下から最上位1頭を選んだ場合の3着以内：{mainstats['candidate_outsider_top1_placed']}/{n} ({pct(mainstats['candidate_outsider_top1_placed'],n)})",""]
    for scope, features in [("レース別","race_features"),("4番人気以下の馬・1頭あたり","horse_features")]:
        lines+=["## "+scope,""]
        for title,values in report[features].items():
            lines+=[f"### {title}","",
                    "|条件|件数|3着以内／事象発生|割合|95%区間|","|---|---:|---:|---:|---|"]
            for label,v in values.items():
                l,u=v["wilson95"]
                lines.append(f"|{label}|{v['n']}|{v['positive']}/{v['n']}|{pct(v['positive'],v['n'])}|{l:.1%}–{u:.1%}|")
            lines+=[""]
    lines+=["## 2026年2日間の別標本と比較","",
            f"- 2026年10/31・11/1公式 {previous['overall']['n']}R：4番人気以下が3着以内 {previous['overall']['any_outsider_top3_count']}R、3着が4番人気以下 {previous['overall']['third_outsider_count']}R。","",
            "## 対象と限界",""]
    lines+=["- "+str(x) for x in report["limitations"]]
    lines+=["","詳細レース別・全出走馬データはJSON原本に保存。",""]
    REPORT.write_text("\n".join(lines)+"\n")
    print(json.dumps({"checked":n,"failed":len(failed),"summary":mainstats,
      "race_features":race_features,"horse_features":horse_features,
      "failure_counts":dict(Counter(f.get("error") for f in failed))},ensure_ascii=False),flush=True)

if __name__=="__main__":main()
