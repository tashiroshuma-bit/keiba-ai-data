"""Auditable offline preparation and pre-off feature generation; no web scraping."""
import csv, datetime as dt, json, math, collections, argparse
from pathlib import Path

FIELDS=['race_id','race_date','off_timestamp','horse_id','horse_number','horse_name','jockey_id','jockey','track','surface','distance_m','gate','carried_weight','body_weight','odds_timestamp','pre_off_odds','finish_position','final_win_odds','source_url']

def load(path):
    with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def stamp(s):
    d=dt.datetime.fromisoformat(s)
    if d.tzinfo is None:raise ValueError('Timezone offset required')
    return d

def validate(rows,cutoff_minutes=5):
    problems=[]; groups=collections.defaultdict(list)
    for row in rows:groups[row.get('race_id','')].append(row)
    for race_id,rs in groups.items():
        if not race_id:problems.append([race_id,'missing race_id']);continue
        if len({r.get('horse_number') for r in rs})!=len(rs):problems.append([race_id,'duplicate horse number'])
        if len(rs)<3:problems.append([race_id,'fewer than 3 horses'])
        for r in rs:
            try:
                off=stamp(r['off_timestamp']); odds=stamp(r['odds_timestamp'])
                if odds>off-dt.timedelta(minutes=cutoff_minutes):raise ValueError('odds too late for cutoff')
                if not (float(r['pre_off_odds'])>1):raise ValueError('bad odds')
                if not r['horse_id'] or not r['jockey_id']:raise ValueError('missing stable horse/jockey ID')
                if not r['source_url']:raise ValueError('missing provenance')
            except (KeyError,ValueError,TypeError) as e:problems.append([race_id,r.get('horse_number',''),str(e)])
    return problems

def historical_features(rows):
    """Prior-only features; rows sorted chronologically, same-day race order by off_timestamp."""
    rows=sorted(rows,key=lambda r:stamp(r['off_timestamp']))
    history=collections.defaultdict(list); out=[]
    for r in rows:
        h=history[r['horse_id']]; prior=h[-4:]
        wins=sum(int(x['finish_position'])==1 for x in prior)
        mean_finish=sum(int(x['finish_position']) for x in prior)/len(prior) if prior else None
        same_distance=sum(abs(int(x['distance_m'])-int(r['distance_m']))<=200 for x in prior)
        same_surface=sum(x['surface']==r['surface'] for x in prior)
        o={**r,'prior_4_starts':len(prior),'prior_4_wins':wins,'prior_4_mean_finish':mean_finish,'prior_4_similar_distance_starts':same_distance,'prior_4_same_surface_starts':same_surface}
        out.append(o)
        if r.get('finish_position','').isdigit():history[r['horse_id']].append(r)
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('--output-dir',default='output');p.add_argument('--cutoff-minutes',type=int,default=5);a=p.parse_args()
    rows=load(a.input);errors=validate(rows,a.cutoff_minutes);dest=Path(a.output_dir);dest.mkdir(parents=True,exist_ok=True)
    (dest/'audit.json').write_text(json.dumps({'rows':len(rows),'race_count':len(set(r.get('race_id') for r in rows)),'errors':errors,'valid':not errors},ensure_ascii=False,indent=2),encoding='utf-8')
    if errors:raise SystemExit(f'{len(errors)} validation errors; see audit.json')
    features=historical_features(rows)
    with (dest/'features.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(features[0]) if features else FIELDS);w.writeheader();w.writerows(features)
    print(f'Validated {len(rows)} runners; wrote features.csv')
if __name__=='__main__':main()
