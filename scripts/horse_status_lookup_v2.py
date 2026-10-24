"""Fast point-in-time horse status reader for prebuilt SQLite cache.
Never query raw historical JRA database during prediction.
"""
import argparse,datetime as dt,json,sqlite3
from pathlib import Path

def summarize(rows):
    n=len(rows)
    def bucket(field):
        out={}
        for r in rows:
            k=str(r[field]);b=out.setdefault(k,[0,0,0]);b[0]+=1;b[1]+=r['finish']==1;b[2]+=r['finish']<=3
        return out
    return dict(starts=n,wins=sum(r['finish']==1 for r in rows),
      seconds=sum(r['finish']==2 for r in rows),thirds=sum(r['finish']==3 for r in rows),
      win_rate=sum(r['finish']==1 for r in rows)/n if n else 0,
      top3_rate=sum(r['finish']<=3 for r in rows)/n if n else 0,
      last_race_date=rows[-1]['race_date'] if n else None,
      surface=bucket('surface'),track=bucket('track'),distance=bucket('distance_m'),
      going=bucket('going'),jockey=bucket('jockey_id'),gate=bucket('gate'),
      recent10=[dict(date=r['race_date'],race_id=r['race_id'],finish=r['finish'],track=r['track'],
        surface=r['surface'],distance=r['distance_m'],going=r['going'],jockey_id=r['jockey_id']) for r in rows[-10:]])
def read_card(cache,card,asof,lag_days=7):
    con=sqlite3.connect('file:'+str(Path(cache).resolve())+'?mode=ro',uri=True)
    con.row_factory=sqlite3.Row
    metadata={r['key']:json.loads(r['value']) for r in con.execute('SELECT * FROM metadata')}
    cutoff=(dt.datetime.fromisoformat(asof)-dt.timedelta(days=lag_days)).date().isoformat()
    if cutoff>metadata['exclusive_history_date']:raise ValueError('CACHE_STALE_FOR_REQUESTED_ASOF')
    output=[]
    for horse in card['runners']:
        hid=horse.get('horse_id');name=horse['horse_name']
        if hid:
            rows=[dict(x) for x in con.execute('SELECT * FROM horse_events WHERE horse_key=? AND race_date<? ORDER BY race_date,race_id',('id:'+str(hid),cutoff))]
            identity='official_id'
        else:
            rows=[dict(x) for x in con.execute('SELECT * FROM horse_events WHERE horse_name=? AND race_date<? ORDER BY race_date,race_id',(name,cutoff))]
            ids={x['horse_id'] for x in rows if x['horse_id']}
            identity='ambiguous_name' if len(ids)>1 else 'name_fallback_unverified'
        output.append(dict(horse_number=horse['horse_number'],horse_name=name,horse_id=hid,identity_status=identity,**summarize(rows)))
    con.close()
    return dict(schema='horse_status_card_v2',race_id=card['race_id'],asof=asof,
      history_exclusive_date=cutoff,horse_count=len(output),horses=output)
if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--cache',required=True);p.add_argument('--roster',required=True)
    p.add_argument('--asof',required=True);p.add_argument('--lag-days',type=int,default=7)
    p.add_argument('--output',required=True);a=p.parse_args()
    card=json.loads(Path(a.roster).read_text())
    result=read_card(a.cache,card,a.asof,a.lag_days)
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('CACHE_LOOKUP_PASS',result['horse_count'])
