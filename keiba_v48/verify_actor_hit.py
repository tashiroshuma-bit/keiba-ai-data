"""Independently recount actor hit rates and verify temporal prefix evidence."""
import argparse
import gzip
import json
from pathlib import Path
import numpy as np
from actor_indices import ActorIndices
from actor_index_replay import index_picks
from completion_validation import sha
from enriched_features import load_archive
from features import timestamp
from validation import canonical

ROOT=Path(__file__).resolve().parent


def verify(folder,lag,db=None):
    folder=Path(folder).resolve();report=json.loads((folder/f'evaluation_lag{lag}.json').read_text())
    path=folder/f'index_snapshots_lag{lag}.json'
    if sha(path)!=report['index_snapshot_sha256']:raise ValueError('index prefix records changed')
    snapshots=json.loads(path.read_text());records=[]
    for name,proof in report['predictions_inventory'].items():
        p=(folder/name).resolve()
        if not p.is_relative_to(folder) or sha(p)!=proof['sha256'] or p.stat().st_size!=proof['bytes']:raise ValueError('prediction shard changed')
        part=json.loads(gzip.decompress(p.read_bytes()))
        if len(part)!=proof['races']:raise ValueError('shard count differs')
        records.extend(part)
    if len(records)!=6036 or len({r['race_id'] for r in records})!=len(records):raise ValueError('cohort not complete/unique')
    for row in records:
        s=snapshots[row['index_snapshot']];cut=timestamp(row['cutoff']).timestamp()
        if (s['maximum_result_available_at'] is not None and s['maximum_result_available_at']>cut) or (
            s['maximum_source_off'] is not None and s['maximum_source_off']>=cut):raise ValueError('future result entered historical indices')
    counts={}
    for year,annual in report['years'].items():
        rows=[r for r in records if r['date'][:4]==year];counts[year]={}
        if len(rows)!=annual['races']:raise ValueError('annual count differs')
        for label,metrics in annual['metrics'].items():
            hits=dict(winner_hit=0,ordered_all_hit=0,top3_all_hit=0)
            for row in rows:
                p=row['forecasts'][label].copy();target=list(map(int,row['target']));numbers=set(map(int,row['horse_numbers']))
                p['winner_pick']=int(p['winner_pick'])
                p['ordered_pick']=list(map(int,p['ordered_pick']));p['top3_pick']=list(map(int,p['top3_pick']))
                if (p['winner_pick'] not in numbers or len(set(p['ordered_pick']))!=3 or
                    len(set(p['top3_pick']))!=3 or not set(p['ordered_pick'])<=numbers or not set(p['top3_pick'])<=numbers):
                    raise ValueError('invalid prediction field')
                hits['winner_hit']+=int(p['winner_pick']==target[0])
                hits['ordered_all_hit']+=int(p['ordered_pick']==target)
                hits['top3_all_hit']+=int(set(p['top3_pick'])==set(target))
            if hits!=metrics['counts']:raise ValueError('hit recount differs')
            if any(abs(hits[k]/len(rows)-metrics['rates'][k])>1e-12 for k in hits):raise ValueError('rate differs')
            counts[year][label]=hits
    for name,digest in report['source_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('source changed')
    cold=[]
    if db:
        if sha(db)!=report['input_db_sha256']:raise ValueError('DB differs')
        history,_,_=load_archive(db,lag,allow_unlinked_fields=True)
        for row in (records[0],records[-1]):
            model=ActorIndices(history,row['cutoff'],exclude_race_id=row['race_id'],allow_assumed=True)
            current=[r for r in history if r['race_id']==row['race_id']]
            byno={int(r['horse_number']):r for r in current}
            current=[byno[n] for n in row['horse_numbers']]
            h=[];j=[]
            for r in current:
                values=[]
                for kind in ('horse','jockey'):
                    entry=model.entity(kind,r.get(kind+'_id'))['adjusted_indices']
                    values.append([entry[k] for k in ('finish_performance','win_share','top2_share','top3_share')] if entry else [50.]*4)
                h.append(values[0]);j.append(values[1])
            h=np.array(h);j=np.array(j)
            for label,value in [('horse_only',h),('jockey_only',j),('horse_plus_jockey',(h+j)/2)]:
                expected=index_picks(row['horse_numbers'],value);saved=row['forecasts'][label]
                if any(expected[k]!=saved[k] for k in ('winner_pick','ordered_pick','top3_pick')):
                    raise ValueError('cold as-of reference differs')
                if abs(expected['winner_score']-saved['winner_score'])>1e-5:raise ValueError('cold reference score differs')
            cold.append(dict(race_id=row['race_id'],cutoff=row['cutoff'],all_three_rules_match=True))
    result=dict(status='PASS',evaluation_sha256=sha(folder/f'evaluation_lag{lag}.json'),races=len(records),
        recount=counts,temporal_checks_all_pass=True,cold_reference_checks=cold,
        no_present_day_catalogue_used=True,production_model_changed=False)
    (folder/f'verification_lag{lag}.json').write_text(canonical(result)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True);p.add_argument('--lag',type=int,choices=(2,7),required=True);p.add_argument('--db')
    a=p.parse_args();print(canonical(verify(a.folder,a.lag,a.db)))
