"""Research-only, reproducible body-weight change audit over canonical JRA SQLite.

Usage:
 python scripts/body_weight_audit.py --database /path/to/canonical.sqlite --output audit.json

No forecast weights are changed. Rows lacking reliable horse ID, measured weight,
previous weight, or finishing position are excluded, not imputed.
"""
import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import sqlite3
from pathlib import Path

WEIGHT_KEYS = ("body_weight", "horse_weight", "weight_kg", "body_weight_kg")
CHANGE_KEYS = ("body_weight_change", "weight_change", "body_weight_diff")
BINS = ((-999,-20,"<=-20"),(-20,-10,"-19..-10"),(-10,-4,"-9..-4"),
        (-4,4,"-3..+3"),(4,10,"+4..+9"),(10,20,"+10..+19"),(20,999,">=+20"))

def number(v):
    if isinstance(v,bool) or v is None:return None
    try:
        x=float(str(v).strip().replace("＋","+").replace("−","-").replace("kg",""))
        return x if math.isfinite(x) else None
    except (ValueError,TypeError):return None

def bucket(x):
    return next((label for lo,hi,label in BINS if lo<=x<hi),None)

def parse_payload(payload):
    try:return json.loads(payload) if payload else {}
    except (TypeError,ValueError):return {}

def read_rows(db):
    conn=sqlite3.connect(Path(db).resolve().as_uri()+"?mode=ro",uri=True)
    conn.row_factory=sqlite3.Row
    try:
        rows=conn.execute("""SELECT r.race_id,r.race_date,r.surface,r.distance_m,
                   x.horse_id,x.horse_number,x.finish_order,x.payload_json
                   FROM annual_report_races r JOIN annual_report_runners x
                   ON r.race_id=x.race_id
                   WHERE r.status='validated_result'
                   ORDER BY r.race_date,r.race_id,x.horse_number""")
        for row in rows:
            item=dict(row)
            payload=parse_payload(item.pop("payload_json"))
            item["payload"]=payload
            yield item
    finally:conn.close()

def analyze(rows):
    prior={}; groups=collections.defaultdict(list); coverage=collections.Counter()
    for row in rows:
        coverage["rows"]+=1
        horse=row.get("horse_id")
        race_date=row.get("race_date")
        if not horse or not race_date:
            coverage["missing_identity_or_date"]+=1;continue
        p=row.get("payload") or {}
        weight=next((n for k in WEIGHT_KEYS if (n:=number(p.get(k))) is not None),None)
        explicit=next((n for k in CHANGE_KEYS if (n:=number(p.get(k))) is not None),None)
        old=prior.get(horse)
        # This study pairs only strictly earlier races. Race-day duplicates are blocked.
        if weight is not None and 300<=weight<=650:
            if old and old[0]<race_date:
                delta=weight-old[1]
                if explicit is not None and abs(delta-explicit)>0.1:
                    coverage["conflicting_explicit_change"]+=1
                else:
                    place=number(p.get("finish_position"))
                    if place is None:place=number(row.get("finish_order"))
                    if place is not None and place>=1 and place==int(place):
                        label=bucket(delta)
                        if label:
                            days=(dt.date.fromisoformat(race_date)-dt.date.fromisoformat(old[0])).days
                            key=(label,row.get("surface") or "unknown",
                                 "short" if (row.get("distance_m") or 0)<1600 else "middle+" ,
                                 "0-35d" if days<=35 else "36-90d" if days<=90 else "91d+")
                            groups[key].append((int(place)==1,int(place)<=3,delta))
                            coverage["paired_valid"]+=1
                    else:coverage["missing_finish"]+=1
            else:coverage["missing_previous"]+=1
            if old is None or old[0]<race_date:prior[horse]=(race_date,weight)
        else:coverage["missing_or_invalid_weight"]+=1
    output=[]
    for key,obs in sorted(groups.items()):
        n=len(obs); wins=sum(x[0] for x in obs); tops=sum(x[1] for x in obs)
        output.append(dict(bucket=key[0],surface=key[1],distance=key[2],rest=key[3],
                           n=n,wins=wins,top3=tops,win_rate=wins/n,top3_rate=tops/n,
                           mean_delta_kg=sum(x[2] for x in obs)/n))
    return {"status":"DESCRIPTIVE_RESEARCH_ONLY_NOT_CAUSAL_NOT_PRODUCTION",
            "coverage":dict(coverage),"cells":output,
            "limitations":["Raw group win rates are confounded by field size, odds, age and ability",
                           "Missing weight/identity is never imputed",
                           "Same-day duplicate identities are ignored as prior",
                           "Backtest against frozen v50 with chronological validation before any adoption"]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--database",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    db=Path(a.database)
    digest=hashlib.sha256()
    with db.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):digest.update(chunk)
    report=analyze(read_rows(db))
    report["database_sha256"]=digest.hexdigest()
    path=Path(a.output)
    if path.exists():raise FileExistsError(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"coverage":report["coverage"],"cells":len(report["cells"])},ensure_ascii=False))
if __name__=="__main__":main()
