"""Independent affine replay against immutable exact-rank prediction records."""
import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(previous,predictions,calibration,evaluation):
    old=json.loads(gzip.decompress(Path(previous).read_bytes()))
    new=json.loads(gzip.decompress(Path(predictions).read_bytes()))
    rule=json.loads(Path(calibration).read_text());report=json.loads(Path(evaluation).read_text())
    assert digest(previous)==report['base_predictions_sha256']
    assert digest(predictions)==report['predictions_sha256']
    assert digest(calibration)==report['calibration_sha256']
    assert len(old)==len(new)==6036
    groups=collections.defaultdict(list);max_error=0
    for before,after in zip(old,new):
        assert before['race_id']==after['race_id'] and before['date']==after['date']
        assert before['horse_numbers']==after['horse_numbers']
        raw=before['candidate'];p=np.array(raw['marginal_probabilities']);n=len(p)
        confidence=p[:,0].max()
        alpha=next(b['alpha'] for b in rule['bands'] if b['lower']<=confidence<b['upper'])
        assert 0<=alpha<1 and alpha==after['alpha']
        expected=(1-alpha)*p+alpha/n
        actual=np.array(after['after']['marginal_probabilities'])
        max_error=max(max_error,float(np.abs(expected-actual).max()))
        assert np.allclose(actual,expected,atol=1e-14,rtol=0)
        assert np.allclose(actual.sum(axis=0),1,atol=1e-12)
        assert np.all(actual.sum(axis=1)<=1+1e-12)
        assert np.all(actual>=0)
        for key in ('winner_pick','top3_pick','ordered_pick','target'):assert after[key]==raw[key]
        label=before['horse_numbers'].index(raw['target'][0])
        onehot=np.zeros(n);onehot[label]=1
        for name,dist,q in (('before',p,raw['joint_target_probability']),
                            ('after',expected,(1-alpha)*raw['joint_target_probability']+alpha/(n*(n-1)*(n-2)))):
            target=after[name]
            assert abs(q-target['joint_target_probability'])<1e-14
            loss=-np.log(dist[label,0]);joint=-np.log(q);brier=np.square(dist[:,0]-onehot).sum()
            assert abs(loss-target['winner_log_loss'])<1e-12
            assert abs(joint-target['joint_log_loss'])<1e-12
            assert abs(brier-target['winner_brier'])<1e-12
            pick=before['horse_numbers'].index(raw['winner_pick'])
            assert abs(dist[pick,0]-target['winner_confidence'])<1e-12
        assert int(after['winner_pick']==after['target'][0])==after['after']['winner_hit']
        assert int(after['ordered_pick']==after['target'])==after['after']['ordered_all_hit']
        assert int(set(after['top3_pick'])==set(after['target']))==after['after']['top3_all_hit']
        groups[before['date'][:4]].append(after)
    years={}
    for year,rows in groups.items():
        for stage in ('before','after'):
            for key in ('winner_log_loss','joint_log_loss','winner_brier','winner_hit','ordered_all_hit','top3_all_hit'):
                assert abs(np.mean([r[stage][key] for r in rows])-report['years'][year][stage][key])<1e-12
            ece=0
            for lo,hi in ((0,.2),(.2,.4),(.4,.6),(.6,.8),(.8,1.00000001)):
                part=[r[stage] for r in rows if lo<=r[stage]['winner_confidence']<hi]
                if part:ece+=abs(sum(r['winner_confidence']-r['winner_hit'] for r in part))/len(rows)
            assert abs(ece-report['years'][year][stage]['top_label_ece'])<1e-12
        days=collections.defaultdict(list)
        keys=('winner_log_loss','joint_log_loss','winner_brier')
        for r in rows:days[r['date']].append([r['after'][k]-r['before'][k] for k in keys])
        counts=np.array([len(v) for v in days.values()]);totals=np.array([np.sum(v,axis=0) for v in days.values()])
        draws=np.random.default_rng(48).integers(len(counts),size=(1000,len(counts)))
        estimates=totals[draws].sum(axis=1)/counts[draws].sum(axis=1)[:,None]
        years[year]=dict(races=len(rows),paired_day_bootstrap_95pct_delta={k:np.quantile(estimates[:,i],[.025,.975]).tolist() for i,k in enumerate(keys)})
    return dict(verified=True,races=len(new),maximum_probability_replay_error=max_error,years=years,
        predictions_sha256=digest(predictions),calibration_sha256=digest(calibration),
        base_predictions_sha256=digest(previous),rank_decisions_changed=0,
        independent_features_rebuilt=False,independent_joint_MAP_replayed=False,
        scope='Affine probabilities, labels, picks, cohort and proper scores; base feature and joint MAP verification retained from prior evidence')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('previous','predictions','calibration','evaluation','output'):p.add_argument('--'+k,required=True)
    a=p.parse_args();r=verify(a.previous,a.predictions,a.calibration,a.evaluation)
    Path(a.output).write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r))
