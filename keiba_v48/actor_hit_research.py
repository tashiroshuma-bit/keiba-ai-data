"""Initial historical hit-rate benchmark of separate horse and jockey indices."""
import argparse
import collections
import datetime as dt
import gzip
import hashlib
import json
import pickle
from pathlib import Path
import numpy as np
from actor_index_replay import ActorReplay,index_picks
from completion_validation import sha
from enriched_features import load_archive
from features import timestamp
from validation import canonical

ROOT=Path(__file__).resolve().parent
KEYS=('winner_hit','ordered_all_hit','top3_all_hit')


def hit_record(picks,target):
    return {**picks,'winner_hit':int(int(picks['winner_pick'])==target[0]),
        'ordered_all_hit':int(list(map(int,picks['ordered_pick']))==target),
        'top3_all_hit':int(set(map(int,picks['top3_pick']))==set(target))}


def summary(records):
    return dict(races=len(records),counts={k:sum(r[k] for r in records) for k in KEYS},
        rates={k:sum(r[k] for r in records)/len(records) for k in KEYS},
        tied_top1_races=sum(r.get('tied_top1',False) for r in records))


def intervals(rows,label):
    days=collections.defaultdict(list)
    for r in rows:days[r['date']].append([r['forecasts'][label][k]-r['forecasts']['previous_calibrated'][k] for k in KEYS])
    totals=np.array([np.sum(v,axis=0) for v in days.values()]);counts=np.array([len(v) for v in days.values()])
    rng=np.random.default_rng(48);draws=rng.integers(len(counts),size=(1000,len(counts)))
    values=totals[draws].sum(axis=1)/counts[draws].sum(axis=1)[:,None]
    return {k:np.quantile(values[:,i],[.025,.975]).tolist() for i,k in enumerate(KEYS)}


def run(db,cache,output,lag):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if (output/f'evaluation_lag{lag}.json').exists():raise ValueError('fresh output required')
    protocol=json.loads((ROOT/'ACTOR_HIT_PROTOCOL.json').read_text());dbhash=sha(db)
    state=json.loads((ROOT.parent/'PROJECT_STATE.json').read_text())
    if dbhash!=state['database']['sha256']:raise ValueError('canonical DB required')
    with (Path(cache)/f'features_lag{lag}.pkl').open('rb') as f:stored=pickle.load(f)
    if stored['identity']['db']!=dbhash or stored['identity']['lag']!=lag:raise ValueError('feature cache DB/lag differs')
    for name,digest in stored['identity']['sources'].items():
        if sha(ROOT/name)!=digest:raise ValueError('feature cache source changed')
    source=ROOT/'reports/evidence_rank';reference={};reference_hashes={}
    for name,proof in json.loads((source/f'prediction_inventory_lag{lag}.json').read_text()).items():
        if sha(source/name)!=proof['sha256']:raise ValueError('saved comparison changed')
        reference_hashes[name]=proof['sha256']
        for r in json.loads(gzip.decompress((source/name).read_bytes())):reference[r['race_id']]=r
    races=[r for r in stored['races'] if r['race_id'] in reference]
    races.sort(key=lambda r:(timestamp(r['off_timestamp']),r['race_id']))
    if len(races)!=6036 or len(reference)!=6036:raise ValueError('full comparison cohort required')
    history,_,source_audit=load_archive(db,lag,allow_unlinked_fields=True)
    replay=ActorReplay(history)
    print(canonical(dict(stage='history_ready',lag=lag,fields=len(replay.events),rows=len(replay.h))),flush=True)
    allrows=[]
    for i,race in enumerate(races):
        previous=reference[race['race_id']];numbers=[int(r['horse_number']) for r in race['rows']]
        target=list(map(int,previous['candidate']['target']))
        if list(map(int,previous['horse_numbers']))!=numbers:raise ValueError('comparison roster differs')
        current=[int(r['horse_number']) for r in sorted(race['rows'],key=lambda r:int(r.get('finish_position') or 999))[:3]]
        if current!=target:raise ValueError('comparison target differs')
        cutoff=min(timestamp(f['cutoff_timestamp']) for f in race['features'])
        if cutoff>=timestamp(race['off_timestamp']):raise ValueError('cutoff must precede off')
        snapshot=replay.fit_before(cutoff)
        h,j,hn,jn=replay.scores(race['rows'])
        forecasts={label:hit_record(index_picks(numbers,values),target) for label,values in
                   [('horse_only',h),('jockey_only',j),('horse_plus_jockey',(h+j)/2)]}
        for source_key,label in [('baseline','previous_rank'),('candidate','previous_calibrated')]:
            forecasts[label]=hit_record({k:previous[source_key][k] for k in ('winner_pick','ordered_pick','top3_pick')},target)
        allrows.append(dict(race_id=race['race_id'],date=race['rows'][0]['race_date'],cutoff=cutoff.isoformat(),
            target=target,horse_numbers=numbers,index_snapshot=snapshot['number'],
            horse_adjusted_starts=hn,jockey_adjusted_starts=jn,
            index_input_sha256=hashlib.sha256(canonical(dict(horse=np.round(h,8).tolist(),jockey=np.round(j,8).tolist())).encode()).hexdigest(),
            forecasts=forecasts))
        if (i+1)%1000==0:print(canonical(dict(stage='replay',lag=lag,races=i+1,snapshots=len(replay.snapshots))),flush=True)
    reports={};inventory={}
    labels=['previous_rank','previous_calibrated']+protocol['rules']
    for year in protocol['evaluation_years']:
        rows=[r for r in allrows if r['date'][:4]==str(year)]
        if len(rows)!=(3329 if year==2025 else 2707):raise ValueError('year coverage differs')
        reports[str(year)]=dict(races=len(rows),metrics={label:summary([r['forecasts'][label] for r in rows]) for label in labels},
            paired_day_bootstrap_95pct_delta_vs_calibrated={label:intervals(rows,label) for label in protocol['rules']},
            coverage=dict(mean_horse_index_fraction=float(np.mean([sum(n>0 for n in r['horse_adjusted_starts'])/len(r['horse_numbers']) for r in rows])),
                          mean_jockey_index_fraction=float(np.mean([sum(n>0 for n in r['jockey_adjusted_starts'])/len(r['horse_numbers']) for r in rows]))))
        for start in range(0,len(rows),1000):
            p=output/f'predictions_lag{lag}_{year}_{start//1000:02d}.json.gz'
            p.write_bytes(gzip.compress(canonical(rows[start:start+1000]).encode(),mtime=0))
            inventory[p.name]=dict(sha256=sha(p),bytes=p.stat().st_size,races=len(rows[start:start+1000]))
        print(canonical(dict(stage='evaluation',lag=lag,year=year,metrics=reports[str(year)]['metrics'])),flush=True)
    snapshots=output/f'index_snapshots_lag{lag}.json'
    snapshots.write_text(canonical(replay.snapshots)+'\n')
    report=dict(schema='keiba-actor-hit-evaluation-v1',input_db_sha256=dbhash,lag_days=lag,protocol=protocol,
        years=reports,reference_prediction_hashes=reference_hashes,index_snapshot_sha256=sha(snapshots),
        snapshots=len(replay.snapshots),maximum_solver_step=max(s['maximum_normal_equation_step'] for s in replay.snapshots),
        source_sha256={name:sha(ROOT/name) for name in ('actor_indices.py','actor_index_replay.py','actor_hit_research.py','ACTOR_HIT_PROTOCOL.json')},
        rejected_history_fields=dict(replay.rejected),historical_availability='assumed_calendar_day_lag_for_research_only',
        predictions_inventory=inventory,database_unchanged=sha(db)==dbhash,production_model_changed=False,formal_forward_added=0,
        new_classifier_trained=False,no_post_evaluation_rule_selection=True)
    if not report['database_unchanged']:raise ValueError('DB changed')
    (output/f'evaluation_lag{lag}.json').write_text(canonical(report)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('db','cache','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--lag',type=int,choices=(2,7),required=True)
    a=p.parse_args();run(a.db,a.cache,a.output,a.lag)
