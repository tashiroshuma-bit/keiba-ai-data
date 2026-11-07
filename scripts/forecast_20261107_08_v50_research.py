"""Nov 7-8 2026 actual cards -> saved A research probability -> v50 overlay.

Independent, clearly flagged research forecast. Does not impersonate the canonical
SQLite-validated production v50. Fetches only public pre-race card data.
"""
from __future__ import annotations
import concurrent.futures
import datetime as dt
import hashlib
import json
import math
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import forecast_20261031_1101_four_model as legacy
from scripts.v50_rider_overlay import forecast_v50

JST=dt.timezone(dt.timedelta(hours=9))
CONFIG={
"2026-11-07":{
 "東京":("26050501",["dirt","dirt","turf","turf","dirt","dirt","turf","turf","dirt","turf","turf","turf"],"https://sp.jra.jp/JRADB/accessD.html?CNAME=sw01dde0105202605010120261107%2F70"),
 "京都":("26080501",["dirt","turf","dirt","turf","turf","dirt","dirt","obstacle","turf","dirt","dirt","turf"],"https://sp.jra.jp/JRADB/accessD.html?CNAME=sw01dde0108202605010120261107%2F4E"),
 "福島":("26030301",["dirt","turf","dirt","dirt","turf","turf","turf","dirt","turf","turf","turf","dirt"],"https://sp.jra.jp/JRADB/accessD.html?CNAME=sw01dde0103202603010120261107%2F7A")},
"2026-11-08":{
 "東京":("26050502",["dirt","turf","turf","dirt","turf","dirt","dirt","dirt","turf","dirt","turf","turf"],"https://sp.jra.jp/JRADB/accessD.html?CNAME=sw01dde0105202605020120261108%2FA0"),
 "京都":("26080502",["dirt","dirt","turf","dirt","turf","turf","dirt","turf","dirt","turf","dirt","turf"],"https://sp.jra.jp/JRADB/accessD.html?CNAME=sw01dde0108202605020120261108%2F7E"),
 "福島":("26030302",["dirt","turf","dirt","obstacle","obstacle","dirt","turf","dirt","turf","dirt","turf","turf"],"https://sp.jra.jp/JRADB/accessD.html?CNAME=sw01dde0103202603020120261108%2FAA")}
}

def hashfile(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read_ids():
    # Actual named jockey -> official identity mappings from previous published official snapshots.
    path=ROOT/"reports/odds_refresh_20261101_morning/PREDICTIONS.json"
    out={}
    if path.exists():
        for race in json.loads(path.read_text()).get("races",[]):
            for horse in race.get("runners",[]):
                if horse.get("jockey_id") and horse.get("jockey"):
                    name=re.sub(r"[ .．　]","",horse["jockey"])
                    out.setdefault(name,horse["jockey_id"])
    return out

def card(task):
    date,track,code,surface,race,seed=task
    label=f"{track}{race}R"
    if surface=="obstacle":
        return {"date":date,"track":track,"race_number":race,"race":label,
                "surface":"obstacle","status":"unsupported_obstacle_model"}
    errors=[]
    # Official JRA roster is preferred and receives independent Yahoo comparison.
    try:
        urls,_=legacy.official_race_urls(date,track)
        horses,roster_sha,weather,going,official_surface,off=legacy.parse_official_roster(
            urls[race],date,track,race)
        if official_surface!=surface:
            raise ValueError("official course differs from schedule")
        try:
            secondary,url,secondary_sha=legacy.parse_internal_roster(date,track,code,race)
            names=lambda hs:{re.sub(r"[\s　]","",h["name"]) for h in hs}
            if names(horses)!=names(secondary):
                raise ValueError("independent roster mismatch")
            secondary_by={re.sub(r"[\s　]","",h["name"]):h for h in secondary}
            for horse in horses:
                if horse.get("career_missing"):
                    alt=secondary_by[re.sub(r"[\s　]","",horse["name"])]
                    for key in ("starts","wins","seconds","thirds"):
                        horse[key]=alt[key]
                    horse["career_missing"]=False
            method="JRA_YAHOO_CROSSCHECK"
        except Exception as exc:
            errors.append("secondary:"+str(exc)[:180])
            method="JRA_ONLY"
        url=urls[race]
    except Exception as exc:
        errors.append("official:"+str(exc)[:180])
        try:
            horses,url,roster_sha=legacy.parse_internal_roster(date,track,code,race)
            method="YAHOO_ONLY_UNVERIFIED_OFFICIAL"
            off=None
        except Exception as second:
            return {"date":date,"track":track,"race_number":race,"race":label,
                    "surface":surface,"status":"failed_card",
                    "errors":errors+["secondary:"+str(second)[:180]]}
    if not 3<=len(horses)<=18 or len({h["number"] for h in horses})!=len(horses):
        return {"date":date,"track":track,"race_number":race,"race":label,
                "surface":surface,"status":"failed_roster","errors":errors}
    if any(h.get("career_missing") or h.get("starts") is None for h in horses):
        return {"date":date,"track":track,"race_number":race,"race":label,
                "surface":surface,"status":"missing_career","errors":errors}
    return {"date":date,"track":track,"race_number":race,"race":label,
            "surface":surface,"status":"card_ready","horses":horses,
            "source":url,"source_sha256":roster_sha,"source_quality":method,
            "original_off_at":off,"errors":errors}

def run():
    legacy.MEETINGS={date:{track:{"code":v[0],"surface":v[1]} for track,v in by.items()}
                     for date,by in CONFIG.items()}
    legacy.JRA_MOBILE_SEEDS={(date,track):v[2] for date,by in CONFIG.items() for track,v in by.items()}
    tasks=[(date,track,v[0],v[1][race-1],race,v[2]) for date,by in CONFIG.items()
           for track,v in by.items() for race in range(1,13)]
    started=dt.datetime.now(JST)
    model,model_sha=legacy.load_model()
    riders=json.loads((ROOT/"reports/v50/horse_adjusted_rider_snapshot_20261029.json").read_text())
    ids=read_ids()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        cards=list(pool.map(card,tasks))
    for r in cards:
        if r["status"]!="card_ready":
            continue
        try:
            hs=r["horses"]
            for h in hs:
                key=re.sub(r"[ .．　]","",h.get("jockey") or "")
                h["jockey_id"]=ids.get(key)
            probs=legacy.internal_probabilities(model,hs,r["track"],r["surface"])
            runners=[{"number":h["number"],"name":h["name"],
                      "jockey_id":h.get("jockey_id"),"p1":p}
                     for h,p in zip(hs,probs)]
            scoped={h["jockey_id"]:riders["residuals"][r["surface"]+":"+h["jockey_id"]]
                    for h in runners if h["jockey_id"] and
                    r["surface"]+":"+h["jockey_id"] in riders["residuals"]}
            # A-D letter labels preserved, B-D unavailable where no verified external score.
            v50=forecast_v50(runners,scoped,weight=1.0,temperature=0.7)
            r["models"]={"A":legacy.calculate_model(hs,probs),"B":None,"C":None,"D":None}
            r["v50"]=v50["v50"]
            r["rider_matched"]=v50["rider_coverage"]
            r["status"]="research_probability_generated"
            r["source_asof"]=started.isoformat()
            r["preoff_at_processing"]=bool(r.get("original_off_at") and
              started<dt.datetime.fromisoformat(r["original_off_at"]))
            r.pop("horses",None)
        except Exception as exc:
            r["status"]="failed_model"
            r["model_error"]=repr(exc)[:280]
    ranking=sorted(({"date":r["date"],"race":r["race"],
                    "horse":r["v50"]["horses"][0]["name"],
                    "number":r["v50"]["horses"][0]["number"],
                    "p1":r["v50"]["horses"][0]["p1"]}
                    for r in cards if r["status"]=="research_probability_generated"),
                    key=lambda x:(-x["p1"],x["date"],x["race"]))
    result={"schema":"weekend-20261107-08-v50-research-v1","version":"v50",
            "standard_forecast":False,
            "status":"RESEARCH_CARD_PROXY_NOT_CANONICAL_V50",
            "started_at":started.isoformat(),"finished_at":dt.datetime.now(JST).isoformat(),
            "model_sha256":model_sha,"rider_snapshot_sha256":hashfile(ROOT/"reports/v50/horse_adjusted_rider_snapshot_20261029.json"),
            "rider_snapshot_cutoff":riders["cutoff_date_exclusive"],
            "full_cards_requested":len(tasks),
            "research_probabilities_generated":len(ranking),
            "failed_or_out_of_domain":len(tasks)-len(ranking),
            "probability_calibration_verified":False,
            "warnings":["Proxy A inputs; not genuine canonical v50 production forecasts.",
                        "B/C/D require matched independent external indices; unavailable here.",
                        "Some Saturday races may have started before collection.",
                        "Jockey residuals are frozen through Oct 18, not a fresh Nov 7 snapshot."],
            "top5_by_date":{day:[x for x in ranking if x["date"]==day][:5] for day in CONFIG},
            "races":cards}
    output=ROOT/"operations/predictions/2026-11-07/v50_weekend_research.json"
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():
        raise FileExistsError("immutable research output already exists")
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    summary=ROOT/"operations/predictions/2026-11-07/v50_weekend_research_summary.md"
    lines=["# 2026-11-07/08 v50 research execution","",
           "**Not canonical v50 production and not validated hit probabilities.**","",
           f"Calculated {len(ranking)}/{len(tasks)} races; omitted {len(tasks)-len(ranking)}.",""]
    for day in CONFIG:
        lines+=["## "+day+" model-internal top five","",
                "|Race|horse|model p1|","|---|---|---:|"]
        for x in result["top5_by_date"][day]:
            lines.append(f"|{x['race']}|{x['number']} {x['horse']}|{x['p1']:.2%}|")
        lines+=["","## "+day+" all races","",
                "|Race|status|horse / model p1|","|---|---|---|"]
        for r in cards:
            if r["date"]!=day:continue
            best=r.get("v50",{}).get("horses",[None])[0]
            value=f"{best['number']} {best['name']} ({best['p1']:.2%})" if best else "—"
            lines.append(f"|{r['race']}|{r['status']}|{value}|")
        lines.append("")
    summary.write_text("\n".join(lines))
    print(json.dumps({"generated":len(ranking),"requested":len(tasks),
                      "top5":result["top5_by_date"],
                      "errors":[{"race":r["race"],"date":r["date"],"status":r["status"],
                                "errors":r.get("errors")} for r in cards
                                if r["status"]!="research_probability_generated"]},ensure_ascii=False))

if __name__=="__main__":
    run()
