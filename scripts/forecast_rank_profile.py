"""Build a research forecast from actual linked history with a frozen profile.

python scripts/forecast_rank_profile.py --db DB --runners CARD_JSON \
  --profile operations/prediction_policy/observed_history_rank.json \
  --lag 7 --ledger LEDGER --output NEW_JSON
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'keiba_v48'))
from completion_validation import sha
from rank_forecast import forecast
from validation import Ledger,canonical


def create(db,rows,profile,lag):
    if profile.get('schema')!='keiba-observed-history-profile-v1' or profile.get('live_eligible') is not False:
        raise ValueError('research profile required')
    if sha(db)!=profile['database_sha256']:raise ValueError('canonical database differs from frozen profile')
    artifact=profile['lags'][str(lag)]
    paths={}
    for kind in ('model','selection','calibration'):
        item=artifact[kind]
        if item is None and kind=='calibration':
            paths[kind]=None
            continue
        path=(ROOT/item['path']).resolve()
        if not path.is_relative_to(ROOT) or sha(path)!=item['sha256']:raise ValueError('profile artifact changed: '+kind)
        paths[kind]=path
    for row in rows:
        if row.get('feature_generation_mode')!='observed_history':raise ValueError('observed-history input mode required')
        if str(row.get('horse_id','')).startswith('unlinked:'):raise ValueError('official identity required; no inferred history join')
        digest=row.get('source_sha256','')
        if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('runner snapshot source hash required')
    result=forecast(db,rows,paths['model'],paths['selection'],paths['calibration'])
    counts=[r['history_starts'] for r in result['runners']]
    result['prediction_basis']=dict(mode='observed_history',mean_imputed_career_proxy=False,
        runners_with_no_observed_history=sum(n==0 for n in counts),
        runners_with_under_three_starts=sum(n<3 for n in counts),
        note='No-history horses remain in the field; probabilities do not imply sufficient individual evidence.')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('db','runners','profile','ledger','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--lag',type=int,choices=(2,7),required=True)
    a=p.parse_args();output=Path(a.output)
    if output.exists():raise ValueError('use a new immutable prediction output path')
    profile=json.loads(Path(a.profile).read_text());rows=json.loads(Path(a.runners).read_text())
    result=create(a.db,rows,profile,a.lag)
    artifact=profile['lags'][str(a.lag)]['model']['path']
    key=Ledger(a.ledger).freeze(result,json.loads((ROOT/artifact).read_text()),mode='forward')
    with output.open('x') as f:f.write(canonical(dict(prediction_id=key,**result))+'\n')
    print(key)
