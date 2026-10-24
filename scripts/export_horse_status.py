"""Produce an as-of historical horse-status SQLite index from the canonical JRA database.
Run: python scripts/export_horse_status.py --db /path/to/jra_2023_2025.sqlite --out horse_status.sqlite
This is research-only; assumes a seven-calendar-day publication lag.
"""
import argparse,collections,datetime as dt,hashlib,json,sqlite3,time
from pathlib import Path
def main():
 a=argparse.ArgumentParser();a.add_argument('--db',required=True);a.add_argument('--out',required=True);a.add_argument('--asof',default='2026-10-25T15:35:00+09:00');a.add_argument('--lag-days',type=int,default=7);z=a.parse_args()
 t=time.perf_counter();cutoff=(dt.datetime.fromisoformat(z.asof)-dt.timedelta(days=z.lag_days)).date().isoformat()
 db=sqlite3.connect('file:'+str(Path(z.db).resolve())+'?mode=ro',uri=True)
 q="""SELECT h.horse_name,h.horse_id,h.payload_json,r.race_date,r.track,r.surface,r.distance_m
 FROM annual_report_runners h JOIN annual_report_races r ON h.race_id=r.race_id
 WHERE r.status='validated_result' AND r.race_date<? ORDER BY r.race_date,h.race_id"""
 groups=collections.defaultdict(list)
 for name,hid,payload,date,track,surface,distance in db.execute(q,(cutoff,)):
  if not name:continue
  p=json.loads(payload);pos=p.get('finish_position')
  if type(pos)!=int or pos<1:continue
  groups[name].append((date,track,surface,distance,pos,hid))
 db.close()
 out=Path(z.out);out.parent.mkdir(parents=True,exist_ok=True)
 con=sqlite3.connect(out);con.execute('DROP TABLE IF EXISTS horse_status')
 con.execute('CREATE TABLE horse_status(name TEXT PRIMARY KEY,horse_id TEXT,identity_status TEXT,starts INTEGER,wins INTEGER,seconds INTEGER,thirds INTEGER,top3_rate REAL,win_rate REAL,last_race_date TEXT,surface_json TEXT,track_json TEXT,recent_json TEXT)')
 batch=[]
 for name,rs in groups.items():
  ids={r[5] for r in rs if r[5]};identity='verified_unique' if len(ids)==1 else 'missing' if not ids else 'ambiguous'
  surf={};track={}
  for r in rs:
   for dest,key in ((surf,r[2]),(track,r[1])):
    x=dest.setdefault(key,[0,0,0]);x[0]+=1;x[1]+=r[4]==1;x[2]+=r[4]<=3
  batch.append((name,next(iter(ids)) if len(ids)==1 else None,identity,len(rs),sum(r[4]==1 for r in rs),sum(r[4]==2 for r in rs),sum(r[4]==3 for r in rs),sum(r[4]<=3 for r in rs)/len(rs),sum(r[4]==1 for r in rs)/len(rs),rs[-1][0],json.dumps(surf,ensure_ascii=False),json.dumps(track,ensure_ascii=False),json.dumps(rs[-5:],ensure_ascii=False)))
 con.executemany('INSERT INTO horse_status VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',batch)
 con.commit()
 assert con.execute('SELECT count(*) FROM horse_status WHERE last_race_date>=?',(cutoff,)).fetchone()[0]==0
 print('STATUS_CACHE_PASS',len(batch),'horses',round(time.perf_counter()-t,3),'sec',out.stat().st_size,'bytes','historical cutoff exclusive',cutoff)
 con.close()
if __name__=='__main__':main()
