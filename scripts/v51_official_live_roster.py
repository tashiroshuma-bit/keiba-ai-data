"""Parse official JRA mobile racecard rows; fail closed on incomplete or ambiguous identity."""
import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup

try:
    from scripts.v51_jra_racecard_capture import extract_ids
except ModuleNotFoundError:
    from v51_jra_racecard_capture import extract_ids

JST = dt.timezone(dt.timedelta(hours=9))
SEX_AGE = re.compile(r"([牡牝セ])\s*(\d{1,2})")
WEIGHT = re.compile(r"(\d{2}(?:\.\d)?)\s*kg")
OFFICIAL = "https://sp.jra.jp/"

def parse_source(raw, *, url, observed_at, race, off_at, track, surface, distance_m):
    if not url.startswith(("https://sp.jra.jp/", "https://www.jra.go.jp/")):
        raise ValueError("OFFICIAL_JRA_SOURCE_REQUIRED")
    observed = dt.datetime.fromisoformat(observed_at.replace("Z","+00:00"))
    off = dt.datetime.fromisoformat(off_at.replace("Z","+00:00"))
    if observed.tzinfo is None or off.tzinfo is None or observed >= off:
        raise ValueError("PREOFF_SOURCE_REQUIRED")
    soup = BeautifulSoup(raw, "lxml")
    runners = []
    for tr in soup.select("tr"):
        horse_td = tr.select_one("td.horse")
        num_td = tr.select_one("td.num")
        jockey_td = tr.select_one("td.jockey")
        if not all((horse_td, num_td, jockey_td)):
            continue
        horse_links = [(a,extract_ids(a,url)[0]) for a in horse_td.select("a[href],a[onclick]")]
        jockey_links = [(a,extract_ids(a,url)[1]) for a in jockey_td.select("a[href],a[onclick]")]
        hlinks = [(a,next(iter(ids))) for a,ids in horse_links if len(ids)==1]
        jlinks = [(a,next(iter(ids))) for a,ids in jockey_links if len(ids)==1]
        if len(hlinks)!=1 or len(jlinks)!=1:
            raise ValueError("OFFICIAL_ID_LINK_AMBIGUOUS")
        number_txt=num_td.get_text(" ",strip=True)
        if not number_txt.isdecimal():
            raise ValueError("HORSE_NUMBER_UNVERIFIED")
        number=int(number_txt)
        name=hlinks[0][0].get_text(" ",strip=True)
        jockey=jlinks[0][0].get_text(" ",strip=True)
        ja=jockey_td.get_text(" ",strip=True)
        sexage=SEX_AGE.search(ja)
        weight=WEIGHT.search(ja)
        if not name or not jockey or not sexage or not weight:
            raise ValueError("RUNNER_AGE_OR_WEIGHT_UNVERIFIED")
        waku=tr.select_one("td.waku")
        gate=None
        if waku:
            candidates=[waku.get_text(" ",strip=True)]
            for tag in waku.select("[alt],[title]"):
                candidates.extend((tag.get("alt",""),tag.get("title","")))
            for item in candidates:
                m=re.search(r"([1-8])",item)
                if m:
                    gate=int(m.group(1));break
        if gate is None:
            # Horse number is NOT a substitute for official frame number.
            raise ValueError("OFFICIAL_GATE_UNVERIFIED")
        runners.append({"number":number,"name":name,"horse_id":"jra:"+hlinks[0][1],
                        "jockey_name":jockey,"jockey_id":"jra:"+jlinks[0][1],
                        "age":int(sexage.group(2)),"female":int(sexage.group(1)=="牝"),
                        "carried_weight":float(weight.group(1)),"gate":gate})
    if len(runners)<3 or len({x["number"] for x in runners})!=len(runners):
        raise ValueError("INCOMPLETE_OR_DUPLICATE_FIELD")
    if len({x["horse_id"] for x in runners})!=len(runners) or len({x["jockey_id"] for x in runners})!=len(runners):
        raise ValueError("DUPLICATE_OFFICIAL_ID")
    runners.sort(key=lambda x:x["number"])
    if [r["number"] for r in runners]!=list(range(1,len(runners)+1)):
        raise ValueError("NONCONTIGUOUS_OFFICIAL_NUMBERS")
    return {"schema":"jra-v51-live-racecard-v1","captured_at":observed_at,
            "source_url":url,"source_sha256":hashlib.sha256(raw).hexdigest(),
            "races":[{"race":race,"race_off_at":off_at,"track":track,"surface":surface,
                      "distance_m":distance_m,"horses":runners}]}

def main():
    p=argparse.ArgumentParser()
    for key in ("html","url","observed-at","race","off-at","track","surface","distance-m","output"):
        p.add_argument("--"+key,required=True)
    a=p.parse_args()
    result=parse_source(Path(a.html).read_bytes(),url=a.url,observed_at=a.observed_at,
                        race=a.race,off_at=a.off_at,track=a.track,surface=a.surface,
                        distance_m=int(a.distance_m))
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"status":"VERIFIED_FULL_FIELD","runners":len(result["races"][0]["horses"])}))
if __name__=="__main__":main()
