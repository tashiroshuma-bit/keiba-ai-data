"""Reconnect B/C/D saved A and v50 rider overlay to public external AI indices.

Uses the existing model mixture A=.00, B=.25, C=.50, D=.75 external.
Strict full roster number/name agreement; no invented scores.
"""
import concurrent.futures
import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from scripts import forecast_20261031_1101_four_model as legacy
from scripts.v50_rider_overlay import forecast_v50

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"operations/predictions/2026-11-07/v50_weekend_research.json"
DEST=ROOT/"operations/predictions/2026-11-07/v50_weekend_abcd_reconnected.json"
REPORT=ROOT/"operations/predictions/2026-11-07/v50_weekend_abcd_report.md"
JST=dt.timezone(dt.timedelta(hours=9))
TRACKS=("東京","京都","福島")
DATES=("2026-11-07","2026-11-08")
WEIGHTS={"A":0.0,"B":0.25,"C":0.50,"D":0.75}

def clean(v):
    return re.sub(r"[\s　．.・]","",v or "")

def get_page_map():
    site="https://muryou-keiba-ai.jp/"
    html=legacy.get(site)
    soup=BeautifulSoup(html,"html.parser")
    pages={}
    for anchor in soup.find_all("a",href=True):
        value=" ".join(anchor.get_text(" ",strip=True).split())
        m=re.search(r"(東京|京都|福島)\s+11月(7|8)日\s+(\d{1,2})R",value)
        if not m: continue
        url=urljoin(site,anchor["href"])
        if re.search(r"/predict/2026/",url):
            key=(f"2026-11-{int(m[2]):02d}",m[1],int(m[3]))
            old=pages.get(key)
            if old and old!=url:raise ValueError("multiple external pages "+str(key))
            pages[key]=url
    return pages,hashlib.sha256(html).hexdigest()

def transform(r,pages,riders):
    result={"race":r["race"],"date":r["date"],"track":r["track"],
            "race_number":r["race_number"],"status":r["status"]}
    if r["status"]!="research_probability_generated":
        return result
    key=(r["date"],r["track"],r["race_number"])
    if key not in pages:
        result["status"]="external_link_missing"
        return result
    try:
        external,updated,external_sha=legacy.parse_external(
            pages[key],*key)
        field=r["models"]["A"]["horses"]
        a_by_no={h["number"]:h for h in field}
        e_by_no={h["number"]:h for h in external}
        if len(a_by_no)!=len(field) or len(e_by_no)!=len(external):
            raise ValueError("duplicate horse number")
        if set(a_by_no)!=set(e_by_no):
            raise ValueError("full roster number mismatch")
        if any(clean(a_by_no[n]["name"])!=clean(e_by_no[n]["name"])
               for n in a_by_no):
            raise ValueError("full roster name mismatch")
        # Source page timestamp is evidence. Do not use updated-after-off
        # as a preoff forecast even when the race itself was in the past.
        original_off=r.get("original_off_at")
        if updated and original_off:
            if dt.datetime.fromisoformat(updated)>dt.datetime.fromisoformat(original_off):
                raise ValueError("external published after race off")
        if not updated:
            result["external_preoff_proven"]=False
        else:
            result["external_preoff_proven"]=bool(original_off)
        ordered=sorted(field,key=lambda h:h["number"])
        external_p=legacy.softmax([e_by_no[h["number"]]["index"] for h in ordered])
        base=[h["p1"] for h in ordered]
        total=sum(base)
        if abs(total-1)>1e-6:
            raise ValueError("invalid original A probabilities")
        # Rider identity: A calculation's same runner labels from the prior
        # external-card job preserved only in rider coverage, not IDs. Thus
        # reconstruct v50 B-D from A->v50 per-horse log-ratio, up to constant.
        av50={h["number"]:h["p1"] for h in r["v50"]["horses"]}
        ratio={h["number"]:0.7*math.log(av50[h["number"]])-math.log(h["p1"])
               for h in ordered}
        models={"A":r["v50"]}
        for label,alpha in WEIGHTS.items():
            if label=="A":continue
            mixed=[(1-alpha)*a+alpha*e for a,e in zip(base,external_p)]
            # p50 ∝ exp((ln p_mixed + rider residual)/0.7).
            # ratio = rider residual - shared log normalizer constant.
            logits=[(math.log(p)+ratio[h["number"]])/0.7
                    for h,p in zip(ordered,mixed)]
            top=max(logits)
            w=[math.exp(x-top) for x in logits]
            sm=sum(w)
            from scripts.jockey_overlay_ticket_math import calculate_model
            models[label]=calculate_model(ordered,[v/sm for v in w])
        result.update({"status":"abcd_reconnected",
            "external_url":pages[key],"external_sha256":external_sha,
            "external_updated_at":updated,
            "external_preoff_proven":result.get("external_preoff_proven",False),
            "external_indices":{str(n):e_by_no[n]["index"] for n in sorted(e_by_no)},
            "models":models,"weights":WEIGHTS})
    except Exception as exc:
        result.update({"status":"external_rejected","reason":str(exc)[:300],
                      "external_url":pages[key]})
    return result

def main():
    original=SRC.read_bytes()
    source=json.loads(original)
    pages, listing_sha=get_page_map()
    if len(pages)<60:
        raise RuntimeError("External listing insufficient: "+str(len(pages)))
    entries=source["races"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        races=list(pool.map(lambda r:transform(r,pages,None),entries))
    ok=[r for r in races if r["status"]=="abcd_reconnected"]
    rejected=[r for r in races if r["status"]=="external_rejected"]
    result={"schema":"v50-abcd-external-reconnection-v1",
        "origin_sha256":hashlib.sha256(original).hexdigest(),
        "external_listing_sha256":listing_sha,
        "external_listing_count":len(pages),
        "reconnected":len(ok),"rejected":len(rejected),
        "requested":len(races),"standard_forecast":False,
        "status":"RESEARCH_BCD_EXTERNAL_BLEND_NOT_INDEPENDENTLY_CALIBRATED",
        "weights":WEIGHTS,"races":races}
    if DEST.exists():raise FileExistsError("no overwrite")
    DEST.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    lines=["# v50 A〜D再接続｜2026-11-07・08","",
        "**研究値：外部予測指数をsoftmax(T=20)で変換して混合。B/C/Dは元のAに25/50/75％混合し、v50の騎手補正＋T=.7を適用。予想的中率の実証ではない。**",
        f"外部リンク取得 {len(pages)}、4モデル接続 {len(ok)}/69平地R、外部照合拒否 {len(rejected)}R。",""]
    for date in DATES:
        lines.extend(["## "+date,"",
            "|R|レース|A ◎/p1|B ◎/p1|C ◎/p1|D ◎/p1|状態|",
            "|---|---|---|---|---|---|---|"])
        for r in races:
            if r["date"]!=date:continue
            row=[str(r["race_number"]),r["race"]]
            for label in WEIGHTS:
                m=r.get("models",{}).get(label)
                h=m["horses"][0] if m else None
                row.append(f"{h['number']} {h['name']} {h['p1']:.2%}" if h else "—")
            row.append(r["status"])
            lines.append("|"+ "|".join(row)+"|")
        lines.append("")
    lines+=["## 照合拒否",""]
    for r in rejected:
        lines.append(f"- {r['date']} {r['race']}: {r['reason']}")
    REPORT.write_text("\n".join(lines)+"\n")
    print(json.dumps({"reconnected":len(ok),"rejected":len(rejected),
        "missing":[[r["date"],r["race"],r.get("reason",r["status"])]
                   for r in races if r["status"]!="abcd_reconnected"]},ensure_ascii=False))

if __name__=="__main__":
    main()
