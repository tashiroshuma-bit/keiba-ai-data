"""Verify and summarize the frozen experiment, without choosing another policy."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'keiba_v48'))
from boosted_race import BoostedRaceModel
from roi95_research import summarize, save


def read(path):
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)


def main():
    dest=ROOT/'keiba_v48/reports/roi95'; summary={}
    for lag in (2,7):
        selection=read(dest/f'selection_lag{lag}.json')
        evaluation=read(dest/f'evaluation_lag{lag}.json')
        for name,digest in selection['source_sha256'].items():
            current=ROOT/'keiba_v48'/name
            archived=dest/'source'/name
            assert any(p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==digest for p in (current,archived)), name
        for family,artifact in selection['model_artifacts'].items():
            path=dest/artifact['path']
            assert hashlib.sha256(path.read_bytes()).hexdigest()==artifact['sha256']
            m=BoostedRaceModel.from_dict(read(path),allow_research=True)
            assert m.family==family
        records=read(dest/f'predictions_lag{lag}.json.gz')
        prior=read(ROOT/f'keiba_v48/reports/deep_audit/repair_predictions_lag{lag}.json.gz')
        assert {p['race_id'] for p in records}=={p['race_id'] for p in prior}
        old={r['race_id']:r for r in prior}
        fixed={r['race_id'] for r in read(ROOT/f'keiba_v48/reports/completion/final_market_decisions_lag{lag}.json')}
        races=[]; baseline=[]; predictions=[]
        choice=evaluation['selected_policy']['policy']
        for p in records:
            r=old[p['race_id']]
            assert r['horse_numbers']==p['horse_numbers'] and r['winner_index']==p['winner_index']
            assert r['final_odds']==p['final_odds']
            for ps in p['predictions'].values():
                assert len(ps)==len(p['horse_numbers']) and np.isfinite(ps).all() and min(ps)>=0 and abs(sum(ps)-1)<1e-8
            rows=[dict(horse_number=n,final_win_odds=o,win_payout_100=p['win_payout_100'],race_date=p['date']) for n,o in zip(p['horse_numbers'],p['final_odds'])]
            races.append(dict(race_id=p['race_id'],rows=rows,winner_index=p['winner_index']))
            baseline.append(r['previous_expanded'])
            predictions.append(p['predictions'][choice['family']])
        previous_same_policy=summarize(races,baseline,choice)[0]
        new_same_policy=summarize(races,predictions,choice)[0]
        assert new_same_policy==evaluation['selected_policy']['exploratory_metrics']
        verification=read(dest/f'verification_lag{lag}.json')
        assert verification['verified'] and verification['independently_recomputed_return_pct']==new_same_policy['return_pct']
        ix=[i for i,r in enumerate(races) if r['race_id'] in fixed]
        fixed_selected=summarize([races[i] for i in ix],[predictions[i] for i in ix],choice)[0]
        summary[str(lag)]=dict(selected_policy=choice,
            calibration=evaluation['selected_policy']['calibration_metrics'],
            full_3314_previous_same_policy=previous_same_policy,
            full_3314_candidate_same_policy=new_same_policy,
            fixed_345_candidate_selected_policy=fixed_selected,
            fixed_345_same_EV={f:v['fixed_345_same_ev'] for f,v in evaluation['families'].items()},
            observed_target_met=evaluation['selected_policy']['observed_target_met'],
            confidence_lower_target_met=evaluation['selected_policy']['confidence_lower_target_met'])
    save(dest/'summary.json',summary)
    inventory={str(p.relative_to(dest)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(dest.rglob('*')) if p.is_file() and p.name!='artifact_inventory.json' and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    save(dest/'artifact_inventory.json',inventory)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
