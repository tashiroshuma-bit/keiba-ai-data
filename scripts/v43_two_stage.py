"""V43 two-stage forecast: immutable pre-race baseline, separately supplied race-day update.

This is an input/forecast revision protocol, not a claim of calibrated model accuracy.
Usage:
 python scripts/v43_two_stage.py prepare --card operations/20261025_kikuka_roster.json --status operations/20261025_kikuka_status_compact.json --output reports/v43_pre.json
 python scripts/v43_two_stage.py revise --baseline reports/v43_pre.json --day-input operations/race_day.json --output reports/v43_final.json
"""
import argparse,datetime as dt,hashlib,json
from pathlib import Path

def stable_hash(obj):
    return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def parse_time(value):
    x=dt.datetime.fromisoformat(value)
    if x.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
    return x
def write_new(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2)
def prepare(card,status):
    runners=card['runners']
    if len(runners)!=len(status['rows']):raise ValueError('STATUS_ROSTER_COUNT_MISMATCH')
    if len({int(x['horse_number']) for x in runners})!=len(runners):raise ValueError('DUPLICATE_RUNNER')
    off=parse_time(card['off_timestamp']);asof=parse_time(status['asof'])
    if asof>off-dt.timedelta(minutes=5):raise ValueError('LATE_STATUS')
    horses=[{'horse_number':int(r['horse_number']),'horse_name':r['horse_name'],
             'cached_status':s} for r,s in zip(runners,status['rows'])]
    result={'schema':'v43_two_stage_pre_v1','race_id':card['race_id'],'off_timestamp':card['off_timestamp'],
            'status_asof':status['asof'],'horses':horses,
            'stage':'PRE_RACE_BASELINE','prediction_status':'AWAITING_RACE_DAY_INFORMATION',
            'formal_eligible':False}
    result['baseline_sha256']=stable_hash(result)
    return result
def revise(baseline,day):
    baseline_copy={k:v for k,v in baseline.items() if k!='baseline_sha256'}
    if stable_hash(baseline_copy)!=baseline['baseline_sha256']:raise ValueError('BASELINE_TAMPERED')
    if day['race_id']!=baseline['race_id']:raise ValueError('RACE_ID_MISMATCH')
    off=parse_time(baseline['off_timestamp'])
    observed=parse_time(day['observed_at']);received=parse_time(day['received_at'])
    if observed>received or received>off-dt.timedelta(minutes=5):
        raise ValueError('DAY_DATA_TOO_LATE_OR_INVALID')
    if not str(day.get('source_url','')).startswith('https://'):
        raise ValueError('DAY_SOURCE_REQUIRED')
    known={h['horse_number']:h for h in baseline['horses']}
    updated={}
    for r in day['runners']:
        no=int(r['horse_number'])
        if no not in known or no in updated:raise ValueError('UNKNOWN_OR_DUPLICATE_RUNNER')
        if r.get('horse_name')!=known[no]['horse_name']:raise ValueError('HORSE_NAME_MISMATCH')
        updated[no]=r
    if set(updated)!=set(known):raise ValueError('INCOMPLETE_DAY_FIELD')
    mandatory=('jockey_id','carried_weight','gate','going','track','surface','distance_m')
    gaps={}
    for no,r in updated.items():
        missing=[k for k in mandatory if r.get(k) in (None,'')]
        if missing:gaps[no]=missing
    # Missing values are flagged; never fabricated or silently mean-imputed.
    result={'schema':'v43_two_stage_revision_v1','race_id':day['race_id'],
            'stage':'RACE_DAY_REVISION','baseline_sha256':baseline['baseline_sha256'],
            'day_input_sha256':stable_hash(day),'observed_at':day['observed_at'],
            'received_at':day['received_at'],'source_url':day['source_url'],
            'horses':[{'horse_number':n,'horse_name':known[n]['horse_name'],
                       'cached_status':known[n]['cached_status'],
                       'race_day':updated[n]} for n in sorted(known)],
            'missing_race_day_fields':gaps,
            'prediction_status':'READY_FOR_MODEL_RECOMPUTE' if not gaps else 'DAY_INPUT_INCOMPLETE',
            'formal_eligible':False,
            'formal_gate_note':'Feature parity, official ID provenance, and model live eligibility require independent verification.'}
    return result
def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('prepare');a.add_argument('--card',required=True);a.add_argument('--status',required=True);a.add_argument('--output',required=True)
    b=sub.add_parser('revise');b.add_argument('--baseline',required=True);b.add_argument('--day-input',required=True);b.add_argument('--output',required=True)
    z=p.parse_args()
    load=lambda x:json.loads(Path(x).read_text(encoding='utf-8'))
    out=prepare(load(z.card),load(z.status)) if z.cmd=='prepare' else revise(load(z.baseline),load(z.day_input))
    write_new(z.output,out)
    print(out['stage'],out['prediction_status'],z.output)
if __name__=='__main__':main()
