"""2026-11-08 AM live market snapshot, strict official runner matching, v50 ABCD updated.
Source JRA racecard, observed timestamp when response bytes were read. No final odds.
No past-off, unsupported jumps, missing odds, withdrawn or roster conflict guessed.
"""
import concurrent.futures
import datetime as dt
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from scripts import forecast_20261031_1101_four_model as legacy
from scripts.forecast_20261107_08_v50_research import CONFIG
from scripts.v50_preoff_odds_blend import combine

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/"operations/predictions/2026-11-07/v50_weekend_abcd_reconnected.json"
OUT=ROOT/"operations/predictions/2026-11-08/v50_live_odds_morning_20261108.json"
MD=ROOT/"operations/predictions/2026-11-08/v50_live_odds_morning_20261108.md"
DAY="2026-11-08"
JST=dt.timezone(dt.timedelta(hours=9))
TRACKS=("東京","京都","福島")
SHARES={"A":0,"B":.25,"C":.50,"D":.75}
def normalize(s):return re.sub(r"[\s　．.・]","",s or "")
def geturls(track):
    raw=legacy.get(CONFIG[DAY][track][2]); soup=BeautifulSoup(raw,"html.parser")
    labels=soup.get_text(" ",strip=True)
    if "2026年11月8日" not in labels or track not in labels:raise ValueError("meeting date/track mismatch")
    urls={1:CONFIG[DAY][track][2]}
    for a in soup.select("a[href]"):
        m=re.fullmatch(r"(\d{1,2})R",a.get_text(" ",strip=True))
        if m:urls[int(m[1])]=urljoin(CONFIG[DAY][track][2],a["href"])
    if set(urls)!=set(range(1,13)):raise ValueError("incomplete official urls")
    return urls

def fetch(task):
    row,url=task
    label=row["race"]
    if row["status"]!="abcd_reconnected":
        return {"race":label,"status":row["status"]}
    try:
        raw=legacy.get(url)
        observed=dt.datetime.now(JST)
        soup=BeautifulSoup(raw,"html.parser")
        runners,*_=legacy.parse_official_html(raw,DAY,row["track"],row["race_number"])
        field={normalize(h["name"]):h for h in runners if not h.get("withdrawn")}
        model_by_name={normalize(h["name"]):h for h in row["models"]["C"]["horses"]}
        if len(field)!=len(model_by_name) or set(field)!=set(model_by_name):
            raise ValueError("official roster differs from model field")
        if any(field[name]["number"]!=h["number"] for name,h in model_by_name.items()):
            raise ValueError("official horse number mismatch")
        # Extract public single-win odds from official field ONLY.
        # Card display odds are not guaranteed to have arrived for each race.
        odds_map={}
        for tr in soup.select("tr"):
            cells=tr.find_all(["th","td"],recursive=False)
            idx=next((i for i,c in enumerate(cells) if c.select_one("a[href*='accessU.html']")),None)
            if idx is None:continue
            name=normalize(cells[idx].select_one("a[href*='accessU.html']").get_text(" ",strip=True))
            if name not in field:continue
            text=cells[idx].get_text(" ",strip=True)
            # search near horse name, before expanded previous-runs block
            compact=text.split("前4走")[0]
            m=re.search(r"(\d+(?:\.\d+)?)\s*[（(]\s*(\d{1,2})番人気",compact)
            if not m:
                # odds often in separate cell to right, odds format "12.3 (5番人気)"
                celltxt=" ".join(c.get_text(" ",strip=True) for c in cells[idx:idx+3])
                celltxt=celltxt.split("前走")[0]
                m=re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*[（(]\s*(\d{1,2})番人気",celltxt)
            if m:
                odds_map[name]={"number":field[name]["number"],"name":field[name]["name"],
                                "odds":float(m[1]),"displayed_popularity":int(m[2])}
        if len(odds_map)!=len(field):
            return {"race":label,"status":"odds_unavailable_or_partial",
                "source":url,"observed_at":observed.isoformat(),
                "horses":len(field),"odds_parsed":len(odds_map),
                "sample":[tr.get_text(" ",strip=True)[:190] for tr in soup.select("tr") if tr.select_one("a[href*='accessU.html']")][:2]}
        if any(x["odds"]<=1 for x in odds_map.values()):
            raise ValueError("zero votes or invalid win odds")
        hs=[odds_map[normalize(h["name"])] for h in row["models"]["C"]["horses"]]
        pop={x["displayed_popularity"] for x in hs}
        if pop!=set(range(1,len(hs)+1)):raise ValueError("popularity ranks missing")
        off=dt.datetime.fromisoformat(DAY)
        # original off time from JRA racecard parse
        *_, off_at=legacy.parse_official_html(raw,DAY,row["track"],row["race_number"])
        off=dt.datetime.fromisoformat(off_at)
        if observed>=off:
            return {"race":label,"status":"already_started_skip_odds","observed_at":observed.isoformat(),
                    "off_at":off_at}
        # Any valid latest displayed source is a provisional preoff observation at
        # download time; never represent as off-minute snapshot.
        snapshot={"phase":"preoff","source_kind":"observed_public_win_odds",
                  "observed_at":observed.isoformat(),"horses":hs}
        values={}
        for model in "ABCD":
            values[model]=combine(row["models"][model],snapshot,alpha=.20,off_at=off_at)
        return {"race":label,"status":"preoff_odds_blended",
                "official_url":url,"official_sha256":hashlib.sha256(raw).hexdigest(),
                "observed_at":observed.isoformat(),"off_at":off_at,
                "weather_going_observed":"JRA racecard only; not fused into forecast",
                "horses":hs,"blended":values}
    except Exception as e:
        return {"race":label,"status":"source_or_validation_failed","error":repr(e)[:350],"official_url":url}

def main():
    raw=INPUT.read_bytes()
    data=json.loads(raw)
    rows=[r for r in data["races"] if r["date"]==DAY]
    if len(rows)!=36:raise ValueError("not 36 races")
    urls={track:geturls(track) for track in TRACKS}
    tasks=[(r,urls[r["track"]][r["race_number"]]) for r in rows]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        items=list(pool.map(fetch,tasks))
    statuses=Counter(x["status"] for x in items)
    if statuses["preoff_odds_blended"]<1:
        raise RuntimeError("no valid current-time odds collected "+str(dict(statuses))+
                           " samples "+str(items[:2]))
    content={"schema":"v50-20261108-am-live-odds-v1",
        "generated_at":dt.datetime.now(JST).isoformat(),
        "source":"JRA official racecards and saved ABCD research model",
        "input_sha256":hashlib.sha256(raw).hexdigest(),
        "odds_rule":"only completed public whole-field preoff odds, with observed timestamp",
        "alpha":.2,"production":False,
        "horse_weight_used":False,
        "actual_today_track_bias_used":False,
        "status_counts":dict(statuses),"races":items}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    if OUT.exists():raise FileExistsError("morning snapshot already exists")
    OUT.write_text(json.dumps(content,ensure_ascii=False,indent=2)+"\n")
    md=["# 2026-11-08 v50 A〜D：当日朝・JRA掲載単勝オッズ20%研究補正","",
        "**予測値は校正未済の研究モデル。オッズ取得時間のスナップショットであり、発走直前確定値ではない。**",
        "馬体重・当日馬場に対する別途補正は未実施。出走済みレースへのオッズ取り込みなし。",
        "オッズ観測時刻："+content["generated_at"],"",
        "状態件数："+str(dict(statuses)),"",
        "|R|状態|C補正後の1着候補|補正後のモデル内勝率|元のC勝率|単勝オッズ|市場順位|市場人気4位以下p3上位候補|",
        "|---|---|---|---:|---:|---:|---:|---|"]
    by_race={r["race"]:r for r in rows}
    for x in items:
        if x["status"]!="preoff_odds_blended":
            md.append("|"+x["race"]+"|"+x["status"]+"|—|—|—|—|—|—|")
            continue
        c=x["blended"]["C"]
        h=c["ranking"][0]
        names={horse["number"]:horse for horse in x["horses"]}
        original=by_race[x["race"]]["models"]["C"]
        before=original["horses"][0]
        holes=c["outsider_third_candidates"][:3]
        ts="、".join(f"{a['number']} {a['name']} p3 {a['v50_p3']:.1%}" for a in holes)
        nd=names[h["number"]]
        md.append(f"|{x['race']}|反映（{x['observed_at'][11:16]}）|{h['number']} {nd['name']}|{h['blend_p1']:.2%}|{before['p1']:.2%}|{nd['odds']:.1f}|{nd['displayed_popularity']}|{ts}|")
    md+=["","## モデルB・C・D別の最終1着候補（オッズが取得できたレースのみ）","",
         "|レース|A|B|C|D|","|---|---|---|---|---|"]
    for x in items:
        if x["status"]!="preoff_odds_blended":continue
        names={h["number"]:h["name"] for h in x["horses"]}
        rank=[f"{x['blended'][k]['ranking'][0]['number']} {names[x['blended'][k]['ranking'][0]['number']]} "
              f"{x['blended'][k]['ranking'][0]['blend_p1']:.1%}" for k in "ABCD"]
        md.append("|"+ "|".join([x["race"]]+rank)+"|")
    md+=["","取得不可レースは前日研究予測の順位を維持し、直前オッズを補完しない。",
         "[前日A〜D出馬表照合済み全36レース](v50_abcd_post_historical_review.md)",""]
    MD.write_text("\n".join(md)+"\n")
    print(json.dumps({"status_counts":dict(statuses),
                      "success":[{"race":x["race"],"observed":x["observed_at"],
                                  "leader":x["blended"]["C"]["ranking"][0]} for x in items
                                if x["status"]=="preoff_odds_blended"]},ensure_ascii=False))

if __name__=="__main__":main()
