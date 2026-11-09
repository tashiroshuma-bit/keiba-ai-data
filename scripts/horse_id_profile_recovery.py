"""Retrospective horse-ID candidate recovery; NOT a prospective feature predictor.

The publication timestamp of a past result is irrelevant to linking a stable
horse identity. Match official horse profile name + birth year against the
historical JRA report's exact name and recorded age. The profile search
evidence is not a race-specific verified official result or raw HTML archive.
Keep its confidence label explicit; do not overwrite the canonical DB.
"""
import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path

def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda:stream.read(1024*1024),b""):h.update(part)
    return h.hexdigest()

def recover(database,profiles):
    conn=sqlite3.connect(Path(database).resolve().as_uri()+"?mode=ro",uri=True)
    try:
        values=conn.execute("""SELECT x.race_id,x.horse_number,x.horse_name,
                 x.horse_id,x.payload_json,r.race_date
                 FROM annual_report_runners x JOIN annual_report_races r USING(race_id)
                 WHERE r.status='validated_result'""").fetchall()
    finally:conn.close()
    known={}
    for rid,num,name,hid,payload,date in values:
        if hid:known.setdefault(name,set()).add(hid)
    candidates={}
    for entry in profiles:
        name=entry["horse_name"];hid=entry["horse_id"]
        year=entry["birth_year"];url=entry["official_profile_url"]
        if name in candidates:raise ValueError("duplicate official profile name")
        if not re.fullmatch(r"jra:[0-9]{10}",hid) or int(hid[4:8])!=year:
            raise ValueError("invalid JRA profile ID and birth year")
        if not str(url).startswith("https://www.jra.go.jp/JRADB/accessU.html?"):
            raise ValueError("official JRA profile is required")
        if hid[4:] not in url:
            raise ValueError("horse ID is not encoded in supplied official profile URL")
        if name in known and known[name]!={hid}:
            raise ValueError("historical name/ID conflict; refuse")
        candidates[name]=entry
    links=[];rejections=[]
    for rid,num,name,hid,payload,date in values:
        if hid is not None or name not in candidates:continue
        p=candidates[name]
        age_match=re.search(r"(?<!\\d)(\\d{1,2})(?!\\d)",json.loads(payload or "{}").get("sex_age") or "")
        if not age_match or int(date[:4])-p["birth_year"]!=int(age_match.group(1)):
            rejections.append({"race_id":rid,"horse_number":num,
                               "horse_name":name,"reason":"birth_year_or_age_mismatch"})
            continue
        links.append({"race_id":rid,"horse_number":num,"horse_name":name,
             "horse_id":p["horse_id"],"race_date":date,
             "source_url":p["official_profile_url"],
             "confidence":"PROFILE_NAME_BIRTHYEAR_AGE_MATCH_NOT_RACEWISE_VERIFIED",
             "raw_original_profile_archived":False})
    links.sort(key=lambda x:(x["race_id"],x["horse_number"]))
    if len({(x["race_id"],x["horse_number"]) for x in links})!=len(links):
        raise ValueError("duplicate result row")
    return {"schema":"horse-id-profile-historical-sidecar-v1",
            "canonical_db_sha256":file_sha(database),
            "status":"RESEARCH_CANDIDATES_NOT_CANONICAL_DB_MUTATION",
            "external_profile_original_bytes_archived":False,
            "official_racewise_verification_complete":False,
            "matched_rows":len(links),"matched_horses":len({x["horse_id"] for x in links}),
            "rejections":rejections,"links":links}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--database",required=True)
    p.add_argument("--profiles",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    out=Path(args.output)
    if out.exists():raise FileExistsError("immutable recovery output must not overwrite")
    report=recover(args.database,json.loads(Path(args.profiles).read_bytes())["profiles"])
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x",encoding="utf8") as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2);stream.write("\n")
    print(json.dumps({"matched_rows":report["matched_rows"],
                      "matched_horses":report["matched_horses"]}))
if __name__=="__main__":main()
