"""Active experimental probability service with observed-history time gates.

Activation retains historical research assumptions. Live history uses actual
source observation times; post-race final odds cannot enter the live input.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sqlite3

from features import HistoryIndex, build_features, timestamp
from fitted_model import HierarchicalModel
from strategy import validate_field, scenario_distribution
from validation import Ledger, canonical


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def activate(model_path, report_path, destination):
    model = json.loads(Path(model_path).read_text())
    report = json.loads(Path(report_path).read_text())
    if digest(model) != report['model_artifact_sha256']:
        raise ValueError('model does not match evaluated artifact')
    HierarchicalModel.from_dict(model, allow_research=True)
    if not model.get('research_only') or report['evaluation_races'] < 1:
        raise ValueError('evaluated research artifact required for experimental activation')
    folder = Path(destination); folder.mkdir(parents=True,exist_ok=True)
    manifest = dict(schema='keiba-active-v1',status='experimental_probability',
                    activated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                    model_file='active_model.json',model_sha256=digest(model),
                    evaluation_report_sha256=digest(report),
                    historical_time_assumptions=True,
                    strict_production_validated=False,
                    history_time_policy='actual_source_observation',
                    missing_jockey_policy='neutral_prior_no_synthetic_id',
                    odds_judgement_policy='post_race_final_reference',
                    live_bet_generation=False,
                    evaluation=dict(races=report['evaluation_races'],
                                    win_top1=report['candidate']['top1_hit'],
                                    fixed_top1_return_pct=report['fixed_top1_100yen']['return_pct']))
    (folder/'active_model.json').write_text(canonical(model),encoding='utf-8')
    (folder/'active_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest


def load_observed_history(db_path, cutoff):
    db = sqlite3.connect('file:' + str(Path(db_path).resolve()) + '?mode=ro',uri=True)
    db.row_factory = sqlite3.Row
    rows=[]
    for r in db.execute('''SELECT r.race_id,r.race_date,r.off_timestamp,r.track,r.surface,r.distance_m,
        r.going,r.expected_runners,r.document_url,h.horse_id,h.jockey_id,h.payload_json,d.fetched_at,
        he.observed_at AS horse_identity_observed_at,je.observed_at AS jockey_identity_observed_at
        FROM annual_report_races r JOIN annual_report_runners h USING(race_id)
        JOIN annual_report_documents d ON d.url=r.document_url
        JOIN annual_identity_links l ON l.race_id=h.race_id AND l.horse_number=h.horse_number
        JOIN official_identity_evidence he ON he.race_id=l.horse_evidence_race_id
          AND he.horse_number=l.horse_evidence_horse_number
        LEFT JOIN official_identity_evidence je ON je.race_id=l.jockey_evidence_race_id
          AND je.horse_number=l.jockey_evidence_horse_number
        WHERE r.status='validated_result' AND h.horse_id IS NOT NULL'''):
        observations=[r['fetched_at'],r['horse_identity_observed_at']]
        if r['jockey_id']:
            observations.append(r['jockey_identity_observed_at'])
        if any(not at for at in observations):
            continue
        at=max(map(timestamp,observations)).isoformat()
        if timestamp(at)>cutoff:
            continue
        payload=json.loads(r['payload_json'])
        if not payload.get('finish_position') or not r['off_timestamp']:
            continue
        rows.append(dict(race_id=r['race_id'],horse_id=r['horse_id'],jockey_id=r['jockey_id'],
                         off_timestamp=r['off_timestamp'],result_available_at=at,
                         availability_basis='observed_archive_result',source_url=r['document_url'],
                         track=r['track'],surface=r['surface'],distance_m=r['distance_m'],going=r['going'],
                         finish_position=payload['finish_position'],field_size=r['expected_runners'],
                         final_win_odds=payload.get('final_win_odds')))
    db.close()
    return HistoryIndex(rows,allow_missing_jockey=True)


def forecast(db_path, rows, manifest_path):
    path=Path(manifest_path)
    manifest=json.loads(path.read_text())
    if manifest.get('schema')!='keiba-active-v1' or manifest.get('status')!='experimental_probability':
        raise ValueError('active experimental manifest required')
    model_path=path.parent/manifest['model_file']
    if model_path.resolve().parent != path.parent.resolve():
        raise ValueError('model must reside beside manifest')
    artifact=json.loads(model_path.read_text())
    if digest(artifact)!=manifest['model_sha256']:
        raise ValueError('active model checksum mismatch')
    for row in rows:
        if any(row.get(f) not in (None,'') for f in ('final_win_odds','finish_position','win_payout_100')):
            raise ValueError('post-race fields cannot enter a live forecast')
        if not row.get('features_asof'):
            raise ValueError('live runner snapshot timestamp required')
        if any(row.get(k) and timestamp(row[k]) > dt.datetime.now(dt.timezone.utc)
               for k in ('features_asof','going_asof')):
            raise ValueError('runner snapshot cannot be from the future')
    cutoff=validate_field(rows,require_odds=False)
    if dt.datetime.now(dt.timezone.utc)>cutoff:
        raise ValueError('live prediction cutoff has already passed')
    if timestamp(manifest['activated_at'])>cutoff:
        raise ValueError('active model was not available at prediction cutoff')
    model=HierarchicalModel.from_dict(artifact,allow_research=True)
    history=load_observed_history(db_path,cutoff)
    features=build_features(history,rows)
    if len({f['horse_id'] for f in features})!=len(features):
        raise ValueError('duplicate canonical horse ID')
    rank,_,_,_=scenario_distribution(model,features)
    output=[]
    for r,f,ps in zip(rows,features,rank):
        output.append(dict(horse_number=str(r['horse_number']),horse_id=f['horse_id'],jockey_id=f['jockey_id'],
                           p_first=ps[0],p_second=ps[1],p_third=ps[2],p_top3=sum(ps),
                           fair_win_odds=1/ps[0],required_win_odds_for_5pct_margin=1.05/ps[0],
                           previous_final_win_odds=f['previous_final_win_odds'],
                           jockey_identity_missing=f['jockey_identity_missing'],history_starts=f['history_starts']))
    return dict(version='4.8',deployment_status='experimental_probability',
                race_id=rows[0]['race_id'],off_timestamp=rows[0]['off_timestamp'],
                cutoff_timestamp=cutoff.isoformat(),runners=output,
                history_time_policy='actual_source_observation',
                historical_model_time_assumptions=True,
                odds_basis='previous_completed_races_only',
                allocation=dict(bets=[],stake_yen=0,gate_reasons=['no live odds; final-odds judgement runs after the result']),
                inputs=dict(runners=rows,features=features),active_model_sha256=manifest['model_sha256'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('activate'); a.add_argument('--model',required=True)
    a.add_argument('--report',required=True);a.add_argument('--output-dir',required=True)
    q=sub.add_parser('predict');q.add_argument('--db',required=True);q.add_argument('--runners',required=True)
    q.add_argument('--manifest',required=True);q.add_argument('--ledger',required=True);q.add_argument('--output',required=True)
    args=p.parse_args()
    if args.command=='activate':
        print(canonical(activate(args.model,args.report,args.output_dir)))
    else:
        rows=json.loads(Path(args.runners).read_text())
        result=forecast(args.db,rows,args.manifest)
        manifest=json.loads(Path(args.manifest).read_text())
        artifact=json.loads((Path(args.manifest).parent/manifest['model_file']).read_text())
        key=Ledger(args.ledger).freeze(result,artifact,mode='forward')
        Path(args.output).write_text(canonical({'prediction_id':key,**result}),encoding='utf-8')
        print(key)
