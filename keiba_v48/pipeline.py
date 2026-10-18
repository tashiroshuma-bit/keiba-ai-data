"""Point-in-time CSV ingestion and race-level quality audit. Stdlib only."""
import csv, json, argparse
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REQUIRED=('race_id','race_date','cutoff_timestamp','horse_id','horse_number','odds_timestamp','win_odds','finish_position','source_url')
OPTIONAL=('horse_name','jockey_id','trainer_id','gate','sex','age','carried_weight','body_weight','body_weight_change','features_asof','last_race_date','last_race_finish','last_race_distance','last_race_surface','track_condition_asof','prior_turf_race_bias_asof','win_payout_100')
FIELDS=REQUIRED+OPTIONAL

def dt(s):
    if not s: raise ValueError('missing timestamp')
    d=datetime.fromisoformat(s)
    if d.tzinfo is None: raise ValueError('timestamp must contain timezone')
    return d

def audit(rows):
    grouped=defaultdict(list)
    for r in rows: grouped[r['race_id']].append(r)
    report=[]
    for rid,rs in sorted(grouped.items()):
        errors=[]
        if len({r['horse_id'] for r in rs})!=len(rs): errors.append('duplicate horse_id')
        if len({r['horse_number'] for r in rs})!=len(rs): errors.append('duplicate horse_number')
        if len({r['cutoff_timestamp'] for r in rs})!=1: errors.append('inconsistent cutoff')
        if len({r['race_date'] for r in rs})!=1: errors.append('inconsistent race date')
        if not all(r['source_url'].startswith(('https://','http://')) for r in rs): errors.append('missing source URL')
        for r in rs:
            try:
                cutoff=dt(r['cutoff_timestamp'])
                if dt(r['odds_timestamp'])>cutoff: errors.append('odds timestamp after cutoff')
                if r.get('features_asof','') and dt(r.get('features_asof',''))>cutoff: errors.append('feature timestamp after cutoff')
                if r.get('last_race_date','') and r.get('last_race_date','')>=r['race_date']: errors.append('last race not before target race')
                if float(r['win_odds'])<=1: errors.append('invalid win odds')
                if int(r['finish_position'])<1: errors.append('invalid finish')
            except (ValueError,TypeError): errors.append('invalid value or timestamp')
        finishes=[int(r['finish_position']) for r in rs if r['finish_position'].isdigit()]
        if len(finishes)!=len(rs) or sorted(finishes)!=list(range(1,len(rs)+1)):
            errors.append('incomplete field, dead heat, or missing finish: manual handling required')
        # Require explicit confirmation that the complete field is present; no silent subset inference.
        if not all(r.get('field_complete','')=='yes' for r in rs): errors.append('full field not attested')
        report.append({'race_id':rid,'runners':len(rs),'eligible':not errors,'errors':sorted(set(errors))})
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('input');ap.add_argument('--output',default='audit.json');args=ap.parse_args()
    with open(args.input,encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    missing=set(REQUIRED)-set(rows[0] if rows else [])
    if missing: raise SystemExit('Missing columns: '+', '.join(sorted(missing)))
    result=audit(rows)
    Path(args.output).write_text(json.dumps({'races':result,'eligible':sum(x['eligible'] for x in result),'total':len(result)},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'eligible':sum(x['eligible'] for x in result),'total':len(result)},ensure_ascii=False))
if __name__=='__main__': main()
