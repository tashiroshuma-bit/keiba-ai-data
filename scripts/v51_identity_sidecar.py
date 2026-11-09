"""Auditable identity reconciliation to an immutable sidecar, NOT DB mutation.

Only attach horse IDs where the canonical race/number/name agrees with
official per-runner evidence and exact archived source bytes. Prevents
name-only matches, collisions, and accidental post-off feature leakage.
"""
import argparse
import hashlib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
try:
    from scripts.capture_v50_bodyweight import immutable_save, moment
except ModuleNotFoundError:
    from capture_v50_bodyweight import immutable_save, moment

def normalized(name):
    return "".join(unicodedata.normalize("NFKC",str(name)).split())

def resolve(conn,proofs,archive_dir,*,asof=None):
    rows=conn.execute("""SELECT r.race_id,x.horse_number,x.horse_name,x.horse_id
        FROM annual_report_races r
        JOIN annual_report_runners x ON r.race_id=x.race_id
        WHERE r.status='validated_result'""").fetchall()
    original={(str(rid),int(no)):(name,old) for rid,no,name,old in rows}
    if len(original)!=len(rows):raise ValueError("ambiguous duplicate race/number in canonical DB")
    seen=set();added=[];rejected=[]
    for p in proofs:
        try:
            key=(str(p["race_id"]),int(p["horse_number"]))
            if key in seen:raise ValueError("duplicate evidence for race and horse number")
            seen.add(key)
            if key not in original:raise ValueError("race/horse not in canonical DB")
            name,current=original[key]
            if normalized(name)!=normalized(p["horse_name"]):
                raise ValueError("horse name mismatch")
            if not str(p["horse_id"]).startswith("jra:"):
                raise ValueError("official JRA namespace required")
            if current and current!=p["horse_id"]:
                raise ValueError("conflicts with existing canonical horse ID")
            if not str(p["source_url"]).startswith("https://www.jra.go.jp/"):
                raise ValueError("primary official source URL required")
            sha=p["source_sha256"]
            if not isinstance(sha,str) or not re.fullmatch(r"[0-9a-f]{64}",sha):
                raise ValueError("malformed source SHA256")
            original_source=Path(archive_dir)/(sha+".bin")
            if not original_source.is_file() or original_source.is_symlink():
                raise ValueError("original official source bytes missing")
            h=hashlib.sha256()
            with original_source.open("rb") as stream:
                for chunk in iter(lambda:stream.read(1048576),b""):h.update(chunk)
            if h.hexdigest()!=sha:raise ValueError("original official source digest mismatch")
            observation=moment(p["observed_at"])
            # asof for prospective time-filtered use is mandatory at feature use,
            # not for historical identity reconstruction.
            if asof is not None and observation>moment(asof):
                raise ValueError("ID was only observed after forecast cutoff")
            if current==p["horse_id"]:
                status="already_linked"
            elif current is None or current=="":
                status="verified_new_link"
            else:
                raise ValueError("unapproved identity state")
            added.append({"race_id":key[0],"horse_number":key[1],
                "horse_name":name,"horse_id":p["horse_id"],
                "observed_at":p["observed_at"],"source_url":p["source_url"],
                "source_sha256":sha,"status":status})
        except (KeyError,ValueError,TypeError,OverflowError) as exc:
            rejected.append({"race_id":p.get("race_id"),"horse_number":p.get("horse_number"),
                             "reason":str(exc)})
    return {"status":"VERIFIED_SIDECAR_ONLY_DB_UNCHANGED",
            "source_rows":len(rows),"proofs":len(proofs),
            "verified_new_links":sum(x["status"]=="verified_new_link" for x in added),
            "already_linked":sum(x["status"]=="already_linked" for x in added),
            "rejected":rejected,"verified":added,
            "warnings":["Original source bytes prove integrity, not independent publication timestamp",
                        "No horse record joined by approximate name",
                        "Actual historical data use requires cutoff check at inference"]}

def main():
    ap=argparse.ArgumentParser()
    for k in ("database","evidence","source-archive","output"):
        ap.add_argument("--"+k,required=True)
    ap.add_argument("--asof")
    args=ap.parse_args()
    con=sqlite3.connect(Path(args.database).resolve().as_uri()+"?mode=ro",uri=True)
    try:
        result=resolve(con,json.loads(Path(args.evidence).read_bytes())["proofs"],
                       args.source_archive,asof=args.asof)
    finally:con.close()
    checksum=immutable_save(args.output,result)
    print(json.dumps({"new_links":result["verified_new_links"],
                      "rejected":len(result["rejected"]),"sha256":checksum}))

if __name__=="__main__":main()
