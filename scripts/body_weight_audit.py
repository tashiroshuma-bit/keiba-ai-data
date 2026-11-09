"""Audit official JRA reported body-weight changes in canonical DB.

Numerical change reported in official PDF is present even for an unlinked horse.
Missing/debut observations are retained as a separate bucket. Research only.
"""
import argparse
import collections
import hashlib
import json
import re
import sqlite3
from pathlib import Path

BINS = ((-999,-20,"<=-20"),(-20,-10,"-19..-10"),
        (-10,-4,"-9..-4"),(-4,4,"-3..+3"),
        (4,10,"+4..+9"),(10,20,"+10..+19"),(20,999,">=+20"))

def number(value):
    if value is None or isinstance(value,bool):
        return None
    s=str(value).strip().translate(str.maketrans("＋－−","+--"))
    return float(s) if re.fullmatch(r"[+-]?\d+(?:\.\d+)?",s) else None

def bucket(delta):
    if delta is None or abs(delta)>80: return "unknown"
    return next((name for low,high,name in BINS if low<=delta<high),"unknown")

def analyze(rows):
    groups=collections.defaultdict(list)
    coverage=collections.Counter()
    for row in rows:
        coverage["validated_runner_rows"]+=1
        p=row["payload"]
        body=number(p.get("body_weight_raw"))
        delta=number(p.get("body_weight_change_raw"))
        finish=number(p.get("finish_position"))
        if finish is None: finish=number(row.get("finish_order"))
        field=number(row.get("expected_runners"))
        if body is None or body<300 or body>650:
            coverage["invalid_weight"]+=1
            continue
        if finish is None or field is None or field<3 or finish<1:
            coverage["invalid_finish_or_field"]+=1
            continue
        label=bucket(delta)
        coverage["delta_known" if label!="unknown" else "delta_unknown"]+=1
        groups[row["race_id"]].append((label,int(finish),int(field)))
    # Require observed complete fields with exactly one winner.
    cell=collections.defaultdict(lambda:[0,0,0,0.])
    n_races=0
    for rid,rr in groups.items():
        if not rr or len(rr)!=rr[0][2] or sum(place==1 for _,place,_ in rr)!=1:
            coverage["excluded_incomplete_races"]+=1
            continue
        n_races+=1
        for label,place,field in rr:
            z=cell[label]
            z[0]+=1; z[1]+=int(place==1); z[2]+=int(place<=3); z[3]+=1/field
    return {"status":"DESCRIPTIVE_ONLY_V50_UNCHANGED",
            "complete_races":n_races,"coverage":dict(coverage),
            "cells":[{"bucket":k,"n":v[0],"wins":v[1],"top3":v[2],
                "win_rate":v[1]/v[0],"top3_rate":v[2]/v[0],
                "win_over_field_size_expected":v[1]/v[3]} for k,v in sorted(cell.items())],
            "warnings":["Not v50 paired backtest","Age, form, class and rest confounding not controlled",
                        "Do not infer causality or production model improvement"]}

def canonical_rows(database):
    con=sqlite3.connect(Path(database).resolve().as_uri()+"?mode=ro",uri=True)
    try:
        cursor=con.execute("""SELECT r.race_id,r.expected_runners,x.finish_order,x.payload_json
          FROM annual_report_races r JOIN annual_report_runners x ON r.race_id=x.race_id
          WHERE r.status='validated_result' AND r.race_date IS NOT NULL
          ORDER BY r.race_id,x.horse_number""")
        for rid,field,finish,payload in cursor:
            yield {"race_id":rid,"expected_runners":field,"finish_order":finish,
                   "payload":json.loads(payload)}
    finally: con.close()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--database",required=True);p.add_argument("--output",required=True)
    a=p.parse_args()
    digest=hashlib.sha256()
    with open(a.database,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):digest.update(chunk)
    result=analyze(canonical_rows(a.database))
    result["database_sha256"]=digest.hexdigest()
    output=Path(a.output)
    if output.exists():raise FileExistsError("Refusing overwrite")
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"races":result["complete_races"],"coverage":result["coverage"]},ensure_ascii=False))

if __name__=="__main__":main()
