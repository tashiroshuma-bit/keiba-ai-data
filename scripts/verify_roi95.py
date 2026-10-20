"""Reload saved weights, reconstruct point-in-time inputs and verify evidence."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'keiba_v48'))
from boosted_race import BoostedRaceModel
from completion_validation import pack,sha
from enriched_features import load_archive,history_index
from historical_replay import eligible_split
from roi95_research import save


def read(path):
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)


def verify(db,lag):
    dest=ROOT/'keiba_v48/reports/roi95'
    selection=read(dest/f'selection_lag{lag}.json');evaluation=read(dest/f'evaluation_lag{lag}.json')
    assert sha(db)==selection['input_db_sha256']==evaluation['input_db_sha256']
    assert sha(dest/f'selection_lag{lag}.json')==evaluation['selection_sha256']
    history,fields,_=load_archive(db,lag,allow_unlinked_fields=True)
    packed=pack(history_index(history),fields)
    packed=[r for r in packed if all(x.get('final_win_odds') is not None for x in r['rows'])]
    max_error=0.;replayed=0
    for family,artifact in selection['model_artifacts'].items():
        path=dest/artifact['path'];assert sha(path)==artifact['sha256']
        model=BoostedRaceModel.from_dict(read(path),allow_research=True)
        for year,filename in ((2024,'calibration_predictions'),(2025,'predictions')):
            records=read(dest/f'{filename}_lag{lag}.json.gz')
            end=model.train_end if year==2024 else model.calibration_end
            races=eligible_split(packed,year,end)
            assert [r['race_id'] for r in records]==[r['race_id'] for r in races]
            predictions=model.predict(races,enforce_time=year==2025)
            for r,p,q in zip(races,records,predictions):
                assert p['winner_index']==r['winner_index']
                assert p['horse_numbers']==[x['horse_number'] for x in r['rows']]
                err=float(np.max(np.abs(np.asarray(q)-p['predictions'][family])))
                assert err<1e-13
                max_error=max(max_error,err);replayed+=1
    records=read(dest/f'predictions_lag{lag}.json.gz')
    # Independently read raw official payout evidence, avoiding settlement code.
    connection=sqlite3.connect(Path(db).resolve().as_uri()+'?mode=ro',uri=True)
    proof={rid:json.loads(raw) for rid,raw in connection.execute('select race_id,payouts_json from pdf_payout_evidence')}
    for rid,raw in connection.execute("select race_id,payload_json from enriched_results where status='complete'"):
        proof.setdefault(rid,{}).update(json.loads(raw)['payouts'])
    connection.close()
    hits=0;stake=0;paid=0;matched=0
    policy=evaluation['selected_policy']['policy']
    assert policy['mode']=='maximum_ev' and policy['odds_cap'] is None and policy['threshold']==1.
    for r in records:
        key='win:'+r['horse_numbers'][r['winner_index']]
        assert proof[r['race_id']][key]==r['win_payout_100'];matched+=1
        p=np.asarray(r['predictions'][policy['family']]);odds=np.asarray(r['final_odds'])
        pick=int(np.argmax(p*odds))
        if (p*odds)[pick]<1:
            assert r['decision']['stake_yen']==0
            continue
        assert r['decision']['horse_number']==r['horse_numbers'][pick]
        stake+=100
        if pick==r['winner_index']:
            hits+=1;paid+=proof[r['race_id']][key]
    expected=evaluation['selected_policy']['exploratory_metrics']
    assert stake==expected['stake_yen'] and paid==expected['payout_yen']
    result=dict(lag_days=lag,input_db_sha256=sha(db),replayed_race_predictions=replayed,
                maximum_absolute_probability_error=max_error,official_payout_evidence_matches=matched,
                selected_hits=hits,selected_stake_yen=stake,selected_payout_yen=paid,
                independently_recomputed_return_pct=100*paid/stake,verified=True)
    save(dest/f'verification_lag{lag}.json',result)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--db',required=True);ap.add_argument('--lag',type=int,choices=(2,7),required=True)
    args=ap.parse_args();verify(args.db,args.lag)
