"""Export a current, observed-history horse/jockey index catalogue."""
import argparse
import datetime as dt
import json
from pathlib import Path
from actor_indices import ActorIndices,SETTINGS
from completion_validation import sha
from enriched_features import load_observed_enriched
from validation import canonical

ROOT=Path(__file__).resolve().parent


def run(db,output,asof):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if (output/'snapshot.json').exists():raise ValueError('new immutable index output folder required')
    state=json.loads((ROOT.parent/'PROJECT_STATE.json').read_text());digest=sha(db)
    if digest!=state['database']['sha256']:raise ValueError('canonical database differs')
    at=dt.datetime.fromisoformat(asof)
    if at.tzinfo is None or at>dt.datetime.now(dt.timezone.utc):raise ValueError('observed cutoff required')
    protocol=json.loads((ROOT/'ACTOR_INDICES_PROTOCOL.json').read_text())
    if protocol['settings']!=SETTINGS:raise ValueError('index settings differ from protocol')
    history=load_observed_enriched(db,at)
    print(canonical(dict(stage='observed_history_loaded',rows=len(history))),flush=True)
    model=ActorIndices(history,at);inventory={};counts={}
    for kind in ('horse','jockey'):
        catalogue=[]
        for identity,rows in sorted(model.by_kind[kind].items()):
            entity=model.entity(kind,identity)
            catalogue.append(dict(id=identity,name=rows[-1].get(kind+'_name'),
                observed_starts=entity['overall']['starts'],adjusted_starts=entity['adjusted_starts'],
                counterpart_count=entity['counterpart_count'],adjusted_counterpart_count=entity['adjusted_counterpart_count'],
                indices=entity['adjusted_indices'],sample_support=entity['sample_support'],
                overall=entity['overall']))
        counts[kind]=dict(entities=len(catalogue),adjusted_entities=sum(r['indices'] is not None for r in catalogue))
        for start in range(0,len(catalogue),500):
            path=output/f'{kind}_indices_{start//500:02d}.json'
            path.write_text(canonical(catalogue[start:start+500])+'\n')
            inventory[path.name]=dict(sha256=sha(path),bytes=path.stat().st_size,entities=len(catalogue[start:start+500]))
    # Post-race, as-of-now example. It is explicitly not a backfilled preoff forecast.
    full_ids=[r for r in history if r.get('horse_id') in model.horse and r.get('jockey_id') in model.jockey]
    example=[]
    if full_ids:
        latest=max(full_ids,key=lambda r:(r['off_timestamp'],r['race_id']))['race_id']
        rows=sorted([r for r in history if r['race_id']==latest],key=lambda r:int(r['horse_number']))
        example=model.runners(rows)
        path=output/'postrace_example.json'
        path.write_text(canonical(dict(status='POSTRACE_ASOF_SNAPSHOT_NOT_PREOFF_FORECAST',race_id=latest,asof=at.isoformat(),
            observed_runners=len(rows),expected_runners=rows[0].get('field_size'),
            complete_field=all(r.get('field_size')==len(rows) for r in rows),runners=example))+'\n')
        inventory[path.name]=dict(sha256=sha(path),bytes=path.stat().st_size,runners=len(example))
    snapshot=dict(schema='keiba-actor-index-snapshot-v1',asof=at.isoformat(),created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        input_db_sha256=digest,database_unchanged=sha(db)==digest,source_rows=len(history),audit=model.audit,counts=counts,
        latest_observed_race_date=max((r['race_date'] for r in history),default=None),
        protocol_sha256=sha(ROOT/'ACTOR_INDICES_PROTOCOL.json'),
        code_sha256={name:sha(ROOT/name) for name in ('actor_indices.py','export_actor_indices.py')},
        new_probability_features_activated=False,probability_performance_improvement_claimed=False,
        formal_forward_added=0,production_model_changed=False,inventory=inventory)
    if not snapshot['database_unchanged']:raise ValueError('DB changed during index export')
    (output/'snapshot.json').write_text(canonical(snapshot)+'\n')
    print(canonical(snapshot),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('db','output','asof'):p.add_argument('--'+name,required=True)
    a=p.parse_args();run(a.db,a.output,a.asof)
