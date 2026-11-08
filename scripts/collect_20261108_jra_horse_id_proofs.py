"""Collect 2026-11-08 official JRA horse ID evidence from result-page horse links.

This is POST-RACE proof for identity auditing only. It does NOT retroactively
prove a pre-off horse roster/snapshot. Never link older races by name alone.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.parse import urljoin
from pathlib import Path
from bs4 import BeautifulSoup
import hashlib,json,re

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"operations/results/2026-11-08/v50_abcd_settlement.json"
DEST=ROOT/"operations/results/2026-11-08/jra_official_runner_identity_evidence.json"

def normalize(s):
    return re.sub(r"[\s　．・.]","",str(s or ""))
def extract_id(href):
    # JRA official horse profile link is JRAID in CNAME; no inference from name.
    m=re.search(r"pw01dud10(\d{10})",href,re.I)
    return "jra:"+m.group(1) if m else None

def fetch_one(race):
    if race["status"]!="official_verified":
        return {"race":race["race"],"status":"unverified_settlement"}
    url=race["url"]
    try:
        with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=20) as resp:
            raw=resp.read()
        obs=datetime.now(timezone.utc).isoformat()
        soup=BeautifulSoup(raw,"html.parser")
        plain=soup.get_text(" ",strip=True)
        if "2026年11月8日" not in plain or race["track"] not in plain:
            raise ValueError("wrong JRA date/venue")
        if not re.search(rf"(?<!\d){race['race_number']}R(?!\d)",plain):
            raise ValueError("wrong race number")
        bynumber={int(r["number"]):r for r in race["runners"]}
        found={}
        for tr in soup.find_all("tr"):
            cells=tr.find_all(["td","th"],recursive=False)
            if len(cells)<4:continue
            text=[c.get_text(" ",strip=True) for c in cells]
            if not re.fullmatch(r"\d{1,2}",text[0]) or not re.fullmatch(r"\d{1,2}",text[2]):continue
            number=int(text[2])
            if number not in bynumber:continue
            # Restrict to horse name exact match, race number and official horse CNAME.
            expected=normalize(bynumber[number]["name"])
            hrefs=[a for a in cells[3].select("a[href]") if
                   normalize(a.get_text(" ",strip=True))==expected]
            for a in hrefs:
                href=urljoin(url,a["href"])
                hid=extract_id(href)
                if not hid:continue
                if number in found and found[number]["horse_id"]!=hid:
                    raise ValueError("conflicting official horse IDs")
                found[number]={"horse_number":number,"horse_name":bynumber[number]["name"],
                    "horse_id":hid,"horse_profile_url":href,
                    "source_race_url":url,"source_sha256":hashlib.sha256(raw).hexdigest(),
                    "observed_at":obs,"evidence_kind":"postrace_official_result_horse_profile_link",
                    "retrospective_preoff_eligible":False}
        if len(found)<3:
            snippets=[]
            for tr in soup.find_all("tr"):
                cells=tr.find_all(["td","th"],recursive=False)
                if len(cells)<4:continue
                if not re.fullmatch(r"\\d{1,2}",cells[0].get_text(" ",strip=True)):continue
                links=[(a.get_text(" ",strip=True),a.get("href"))
                       for a in tr.select("a[href]")][:5]
                snippets.append({"cells":[c.get_text(" ",strip=True)[:70] for c in cells[:5]],
                                 "links":links})
                if len(snippets)>=2:break
            raise ValueError("insufficient official horse profile IDs; tr_count="+str(len(soup.select("tr")))+" anchors="+json.dumps([(a.get_text(" ",strip=True)[:28],a.get("href")) for a in soup.select("a[href]")[:8]],ensure_ascii=False)[:750]+" examples "+json.dumps(snippets,ensure_ascii=False)[:700])
        return {"race":race["race"],"race_date":"2026-11-08","track":race["track"],
                "race_number":race["race_number"],"verified_previous_runners":len(bynumber),
                "status":"official_id_links_verified","verified_id_count":len(found),
                "rows":list(found.values()),"observed_at":obs,"source":url,
                "source_sha256":hashlib.sha256(raw).hexdigest()}
    except Exception as ex:
        return {"race":race["race"],"status":"official_id_unavailable",
                "error":str(ex)[:300],"source":url}

def main():
    source=json.loads(SOURCE.read_text())
    races=source["official"]
    if len(races)!=36:raise ValueError("36 official settlement records required")
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(fetch_one,races))
    successes=[r for r in results if r["status"]=="official_id_links_verified"]
    out={"schema":"jra-2026-11-08-official-horse-identity-proof-v1",
         "purpose":"append-only postrace official horse profile identity evidence",
         "never_name_only_link_older_races":True,
         "never_use_as_proof_of_preoff_publication":True,
         "official_races_attempted":36,"official_races_verified":len(successes),
         "horse_ids_verified":sum(r["verified_id_count"] for r in successes),
         "results":results}
    DEST.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"verified_races":out["official_races_verified"],
                      "horse_id_proofs":out["horse_ids_verified"],
                      "failures":[{"race":r["race"],"error":r.get("error")}
                                  for r in results if r["status"]!="official_id_links_verified"]},
          ensure_ascii=False))
if __name__=="__main__":
    main()
