"""Produce evidence-labeled Sunday 2026-11-08 complete ABCD study after official card audit.

Market popularity and preoff odds are NOT known: outsider designations are
conditional, never inferred from model rank. C is provisional from Saturday's
independently unfrozen research comparison, not formally calibrated.
"""
from __future__ import annotations
import concurrent.futures
import datetime as dt
import json,hashlib,re
from collections import Counter
from pathlib import Path

from scripts import forecast_20261031_1101_four_model as legacy
from scripts.forecast_20261107_08_v50_research import CONFIG
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"operations/predictions/2026-11-07/v50_weekend_abcd_reconnected.json"
RESEARCH=ROOT/"operations/predictions/2026-11-07/v50_weekend_research.json"
RESULTS=ROOT/"operations/predictions/2026-11-08/v50_abcd_official_card_audit.json"
REPORT=ROOT/"operations/predictions/2026-11-08/v50_abcd_post_historical_review.md"
DAY="2026-11-08"
TRACKS=("東京","京都","福島")
NOW=dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))

def clean(x):return re.sub(r"[\s　．.・]","",str(x or ""))
def p(x):return f"{x:.2%}"
def get_cards(track):
    try:
        seed=CONFIG[DAY][track][2]
        raw=legacy.get(seed)
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        soup=BeautifulSoup(raw,"html.parser")
        txt=soup.get_text(" ",strip=True)
        if "2026年11月8日" not in txt or track not in txt:
            raise ValueError("JRA day meeting mismatch")
        urls={1:seed}
        for a in soup.select("a[href]"):
            m=re.fullmatch(r"(\d{1,2})R",a.get_text(" ",strip=True))
            if m:urls[int(m[1])]=urljoin(seed,a["href"])
        if set(urls)!=set(range(1,13)):
            raise ValueError("JRA meeting incomplete: "+str(sorted(urls)))
        return urls
    except Exception as exc:
        return {"error":repr(exc)[:250]}

def verify(r,source,urls):
    key=r["race_number"]
    if r["status"]!="abcd_reconnected":
        return {"race":r["race"],"status":r["status"],"reason":"no A-D flat source"}
    url=urls.get(key)
    if not url:return {"race":r["race"],"status":"official_missing","reason":urls.get("error","missing race link")}
    try:
        raw=legacy.get(url)
        parsed,*_=legacy.parse_official_html(raw,DAY,r["track"],key)
        # Official published racecard may include withdrawals; can only
        # accept exactly one-to-one same horse names and number.
        official={clean(h["name"]):int(h["number"]) for h in parsed if not h.get("withdrawn")}
        predicted=r["models"]["C"]["horses"]
        if len(official)!=len(predicted) or len(set(official.values()))!=len(official):
            raise ValueError("complete official field != frozen prediction")
        changes=[]
        for h in predicted:
            name=clean(h["name"])
            if name not in official:
                raise ValueError("horse name not in official field: "+h["name"])
            if int(h["number"])!=official[name]:
                changes.append({"horse":h["name"],"predicted":h["number"],"official":official[name]})
        if changes:
            return {"race":r["race"],"status":"roster_number_mismatch",
                    "changes":changes,"official_url":url,
                    "official_sha256":hashlib.sha256(raw).hexdigest()}
        return {"race":r["race"],"status":"official_field_matched",
                "official_url":url,"official_sha256":hashlib.sha256(raw).hexdigest(),
                "horses":len(official)}
    except Exception as ex:
        return {"race":r["race"],"status":"official_unverified","reason":str(ex)[:300],"official_url":url}

def analyze():
    original=SRC.read_bytes(); data=json.loads(original)
    base=json.loads(RESEARCH.read_text())
    research={r["race"]:r for r in base["races"] if r["date"]==DAY}
    selected=[r for r in data["races"] if r["date"]==DAY]
    if len(selected)!=36:raise ValueError("missing races")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        packs=list(pool.map(get_cards,TRACKS))
    urls={track:value for track,value in zip(TRACKS,packs)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        audit=list(pool.map(lambda r:verify(r,research[r["race"]],urls[r["track"]]),selected))
    byname={a["race"]:a for a in audit}
    safe=[r for r in selected if byname[r["race"]]["status"]=="official_field_matched"]
    # First five by C p1, not overconfident weighted D with Saturday one-day fit.
    best=sorted(safe,key=lambda r:-r["models"]["C"]["horses"][0]["p1"])[:5]
    topids={r["race"] for r in best}
    topids.update(("東京11R","京都11R"))
    lines=["# 2026-11-08｜JRA全36R・v50 A〜D＋歴史的3着穴研究","",
        "**モデル内研究値。正式な独立校正済みv50予測や直前オッズ反映版ではありません。**",
        "11/7の同一33R研究比較ではC本命17/33、A12/33、B16/33、D14/33。"
        "発走前確認23RではC11/23。1日分の結果によるC重視は暫定であり、最適係数は未確定。",
        "直前単勝オッズ・市場人気・馬体重・当日馬場は未反映。"
        "4番人気以下は前日段階で特定しない。モデル順位4位以下を『人気薄』と呼ばない。",
        f"JRA公式馬番・馬名照合成功：{len(safe)}/34平地R。",""]
    for track in TRACKS:
        lines+=["## "+track+"｜12R一覧","",
          "|R|C本命|C p1|A本命 p1|B本命 p1|D本命 p1|本命一致数|公式確認|",
          "|---:|---|---:|---|---|---|---:|---|"]
        for r in selected:
            if r["track"]!=track:continue
            status=byname[r["race"]]["status"]
            if status!="official_field_matched":
                lines.append(f"|{r['race_number']}|—|—|—|—|—|—|{status}|")
                continue
            ms=r["models"]
            c=ms["C"]["horses"][0]
            leader=lambda label:f"{ms[label]['horses'][0]['number']} {ms[label]['horses'][0]['name']} {p(ms[label]['horses'][0]['p1'])}"
            consensus=sum(ms[label]["horses"][0]["number"]==c["number"] for label in "ABCD")
            lines.append(f"|{r['race_number']}|{c['number']} {c['name']}|{p(c['p1'])}|"+
                         "|".join(leader(label) for label in ("A","B","D"))+
                         f"|{consensus}/4|[JRA公式]({byname[r['race']]['official_url']})|")
        lines.append("")
    lines+=["## 注目上位5レース＋重賞｜C中心・全着順確率・3着穴候補研究","",
            "※『穴候補』はここでは**モデル順位4位以下の参考候補**。"
            "市場人気4位以下の確定には発走前オッズが必要。",""]
    for r in selected:
        if r["race"] not in topids:continue
        a=byname[r["race"]]
        lines += [f"### {r['race']}"+("｜重賞" if r["race"] in ("東京11R","京都11R") else ""),"",
                  f"公式出馬表：[JRA]({a.get('official_url','https://www.jra.go.jp/')})",""]
        if a["status"]!="official_field_matched":
            lines += ["公式出馬表照合できず推奨除外。",""]
            continue
        for label in "ABCD":
            hs=r["models"][label]["horses"][:3]
            lines.append(f"{label}：◎{hs[0]['number']} {hs[0]['name']} {p(hs[0]['p1'])}"
                         +" ｜ "+" ／ ".join(f"{h['number']} {h['name']}" for h in hs[1:]))
        lines+=["","**モデルC全頭上位8頭の確率**","",
                "|C順位|馬番|馬名|1着p1|2着p2|3着p3|3着以内|",
                "|---:|---:|---|---:|---:|---:|---:|"]
        horses=r["models"]["C"]["horses"]
        for i,h in enumerate(horses[:8],1):
            lines.append(f"|{i}|{h['number']}|{h['name']}|{p(h['p1'])}|{p(h['p2'])}|"
                         f"{p(h['p3'])}|{p(h['p1']+h['p2']+h['p3'])}|")
        lines+=["","**暫定3着穴観察対象（モデル順位4位以下、人気未確認）**："+
            "、".join(f"{h['number']} {h['name']}（3着 {p(h['p3'])}）"
                     for h in sorted(horses[3:],key=lambda h:-h["p3"])[:3]),""]
        for key,title in (("quinella","馬連"),("trio","3連複")):
            t=r["models"]["C"]["priority"][key]["tickets"][:3]
            lines += [title+"上位3組合せ（C研究用）: "+
                "、".join("-".join(map(str,x["numbers"]))+" "+p(x["p"]) for x in t),""]
        lines.append("---")
    lines+=["","## 過去351Rの3着穴研究の反映方法","",
            "4〜6番人気の各馬3着以内28.5%、7〜9番人気13.5%、10番人気以下5.2%。"
            "これは2025年の事後人気ベースの過去頻度であり、今回の各馬p3への加点には使わない。",
            "直前手動オッズ取得後、4番人気以下を確定しp3降順に候補を抽出する。",
            "単勝オッズを一頭でも取得できなければオッズ補正なし。発走後オッズの使用禁止。",
            "3着穴の選馬的中は独立な翌日以降のサンプルで検証する。",
            "過去分析：[2025年351R](https://github.com/tashiroshuma-bit/keiba-ai-data/blob/main/reports/outsider_top3_history_2025.md)。","",
            "## 未検証レースの詳細",""]
    for r in audit:
        if r["status"]!="official_field_matched":
            lines.append("- "+r["race"]+"："+r["status"]+"／"+r.get("reason",repr(r.get("changes",""))))
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.write_text("\n".join(lines)+"\n")
    result={"day":DAY,"model":"v50 A-D research C emphasis","canonical_production":False,
          "odds_checked_preoff":False,"source_sha256":hashlib.sha256(original).hexdigest(),
          "official_verified":len(safe),"flat":34,
          "status_counts":dict(Counter(x["status"] for x in audit)),
          "top5":[{"race":r["race"],"horse":r["models"]["C"]["horses"][0]["name"],
                  "number":r["models"]["C"]["horses"][0]["number"],
                  "c_p1":r["models"]["C"]["horses"][0]["p1"]} for r in best],
          "races":audit}
    RESULTS.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"official_verified":len(safe),
          "status":result["status_counts"],"top5":result["top5"],
          "not_verified":[r for r in audit if r["status"]!="official_field_matched"]},
          ensure_ascii=False))

if __name__=="__main__":analyze()
