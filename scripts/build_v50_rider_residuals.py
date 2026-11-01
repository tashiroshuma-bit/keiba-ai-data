"""Generate leak-safe horse-ability-adjusted rider residuals from canonical SQLite.

No target-date results are used. Snapshot date must be earlier than forecast date.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path


def build(db_path, forecast_asof, *, history_lag_days=2):
    forecast_time=dt.datetime.fromisoformat(forecast_asof.replace("Z","+00:00"))
    if forecast_time.tzinfo is None:
        raise ValueError("timezone-aware forecast_asof required")
    cutoff=(forecast_time.astimezone(dt.timezone(dt.timedelta(hours=9))).date()-dt.timedelta(days=history_lag_days)).isoformat()
    con=sqlite3.connect(str(db_path))
    rows=con.execute("""
        SELECT r.race_id,r.race_date,r.surface,x.horse_id,x.jockey_id,
               x.finish_order,r.expected_runners
        FROM annual_report_races r JOIN annual_report_runners x ON r.race_id=x.race_id
        WHERE r.status='validated_result' AND r.race_date < ?
          AND r.surface IN ('turf','dirt') AND x.finish_order > 0
        ORDER BY r.race_date,r.race_id,x.horse_number
    """,(cutoff,)).fetchall()
    con.close()
    by_date=defaultdict(lambda:defaultdict(list))
    for race_id,date,surface,horse,jockey,finish,n in rows:
        if horse and jockey and n and n>=3 and finish<=n:
            by_date[date][race_id].append((surface,horse,jockey,finish,n))
    horse_hist=defaultdict(lambda:[0,0.0])
    rider_hist=defaultdict(lambda:[0,0.0])
    races_used=0
    for date in sorted(by_date):
        pending=[]
        for race_id,field in by_date[date].items():
            if len(field)<3:
                continue
            abilities=[(horse_hist[h][1]+1.2)/(horse_hist[h][0]+8)
                       for _,h,_,_,_ in field]
            mean=sum(abilities)/len(abilities)
            for (surface,horse,jockey,finish,n),ability in zip(field,abilities):
                expected=.5+.5*math.tanh(2*(ability-mean))
                observed=(n-finish)/(n-1)
                pending.append((surface,horse,jockey,finish,observed-expected))
            races_used+=1
        # Entire race day is scored against yesterday's history, not same-day results.
        for surface,horse,jockey,finish,residual in pending:
            rider_hist[(surface,jockey)][0]+=1
            rider_hist[(surface,jockey)][1]+=residual
            horse_hist[horse][0]+=1
            horse_hist[horse][1]+={1:1.0,2:.5,3:.25}.get(finish,0)
    residuals={surface+":"+jockey:total/(n+30)
               for (surface,jockey),(n,total) in sorted(rider_hist.items())}
    return {"schema":"v50-asof-horse-adjusted-rider-v1",
            "source":"preoff_horse_ability_adjusted",
            "asof":(dt.datetime.fromisoformat(cutoff).replace(tzinfo=dt.timezone.utc)).isoformat(),
            "forecast_asof":forecast_asof,"cutoff_date_exclusive":cutoff,
            "database_sha256":hashlib.sha256(Path(db_path).read_bytes()).hexdigest(),
            "races_used":races_used,"residuals":residuals}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--database",required=True)
    p.add_argument("--forecast-asof",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    output=Path(a.output)
    if output.exists():
        raise FileExistsError("snapshot cannot be overwritten")
    data=build(a.database,a.forecast_asof)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")


if __name__=="__main__":
    main()
