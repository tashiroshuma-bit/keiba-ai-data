"""Recount exact hits against previously verified, identical race labels."""
import argparse
import collections
import gzip
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'keiba_v48'))
from completion_validation import sha
from exact_rank_model import ExactRankTree
from exact_rank_research import choose,summary
from ranking_model import RankModel


def verify(folder,predictions,reference,lag):
    folder=Path(folder)
    report=json.loads((folder/f'evaluation_lag{lag}.json').read_text())
    selection=json.loads((folder/f'selection_lag{lag}.json').read_text())
    artifact=json.loads((folder/f'model_lag{lag}.json').read_text())
    assert sha(predictions)==report['predictions_sha256']
    assert sha(folder/f'model_lag{lag}.json')==report['model_sha256']==selection['model_sha256']
    assert sha(folder/f'selection_lag{lag}.json')==report['selection_sha256']
    for name,expected in selection['source_sha256'].items():assert sha(ROOT/'keiba_v48'/name)==expected
    model=(ExactRankTree.from_dict(artifact) if artifact['schema']=='keiba-exact-rank-trees-v1' else RankModel.from_dict(artifact))
    assert model.to_dict()==artifact
    baseline=next(g['metrics'] for g in selection['grid'] if g['name']=='incumbent_original')
    chosen,_=choose(selection['grid'],baseline)
    assert chosen['name']==selection['selected']==report['selected']
    reference_rows=json.loads(gzip.decompress(Path(reference).read_bytes()))
    old={r['race_id']:r for r in reference_rows}
    current=json.loads(gzip.decompress(Path(predictions).read_bytes()))
    assert len({r['race_id'] for r in current})==len(current)==len(old)
    assert {r['race_id'] for r in current}==set(old)
    groups=collections.defaultdict(list)
    for r in current:
        target=old[r['race_id']]['candidate']['target']
        assert r['horse_numbers']==old[r['race_id']]['horse_numbers']
        for family in ('baseline','candidate'):
            v=r[family];assert v['target']==target
            if family=='baseline':
                for k in ('winner_pick','ordered_pick','top3_pick'):
                    assert v[k]==old[r['race_id']]['candidate'][k]
            assert len(set(v['ordered_pick']))==len(v['ordered_pick'])==3
            assert len(set(v['top3_pick']))==len(v['top3_pick'])==3
            assert set(v['top3_pick'])<=set(r['horse_numbers'])
            actual=dict(winner_hit=int(v['winner_pick']==target[0]),
                        ordered_all_hit=int(v['ordered_pick']==target),
                        top3_all_hit=int(set(v['top3_pick'])==set(target)),
                        top3_recall=len(set(v['top3_pick'])&set(target))/3)
            assert all(abs(actual[k]-v[k])<1e-12 for k in actual)
            p=np.asarray(v['marginal_probabilities'])
            assert np.isfinite(p).all() and (p>=0).all() and np.max(abs(p.sum(axis=0)-1))<1e-10
            assert np.max(p.sum(axis=1))<=1+1e-10
            groups[r['date'][:4],family].append(v)
    for year,data in report['years'].items():
        assert data['full_coverage'] is True
        for family in ('baseline','candidate'):
            measured=summary(groups[year,family])
            assert measured==data[family]
        assert data['coverage_races']==len(groups[year,'candidate'])
    assert report['maximum_reload_error']==0 and report['database_unchanged'] is True
    return dict(verified=True,races=len(current),lag_days=lag,predictions_sha256=sha(predictions),
        model_sha256=report['model_sha256'],reference_predictions_sha256=sha(reference),
        all_race_coverage_matches_prior=True,all_hit_counts_recomputed=True,
        independent_full_feature_or_joint_MAP_replay=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('directory','predictions','reference'):p.add_argument('--'+key,required=True)
    p.add_argument('--lag',type=int,choices=(2,7),required=True)
    a=p.parse_args();r=verify(a.directory,a.predictions,a.reference,a.lag)
    (Path(a.directory)/f'verification_lag{a.lag}.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r))
