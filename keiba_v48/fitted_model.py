"""Regularized race softmax with shrunk course/surface coefficient deviations.
Structural model never consumes market odds. Calibration uses later validation only.
"""
import math
import numpy as np
from features import FEATURE_NAMES, ENRICHED_FEATURE_NAMES, timestamp


def softmax(scores, temperature=1.0):
    x = np.asarray(scores, dtype=float)
    if x.ndim != 1 or len(x) < 2 or not np.isfinite(x).all():
        raise ValueError('finite full-field scores required')
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError('positive temperature required')
    z = x / temperature
    z -= z.max()
    p = np.exp(np.maximum(z, -700))
    return p / p.sum()


def check_training_race(race, feature_names=FEATURE_NAMES):
    fs = race['features']
    if len(fs) < 3 or len({f['horse_id'] for f in fs}) != len(fs):
        raise ValueError('complete unique field required')
    winner = race['winner_index']
    if isinstance(winner, bool) or not isinstance(winner, int) or not 0 <= winner < len(fs):
        raise ValueError('invalid winner')
    if len({f['group'] for f in fs}) != 1:
        raise ValueError('inconsistent course/surface group')
    if any(f.get('groups', [f['group']]) != fs[0].get('groups', [fs[0]['group']]) for f in fs):
        raise ValueError('inconsistent hierarchy groups')
    off = timestamp(race['off_timestamp'])
    if timestamp(race['result_available_at']) < off:
        raise ValueError('result before off')
    if any(timestamp(f['cutoff_timestamp']) >= off for f in fs):
        raise ValueError('feature cutoff must precede off')
    x = np.asarray([f['values'] for f in fs], dtype=float)
    if x.shape != (len(fs), len(feature_names)) or not np.isfinite(x).all():
        raise ValueError('invalid feature matrix')


class HierarchicalModel:
    def fit(self, races, iterations=400, learning_rate=.08, regularization=.05, feature_names=FEATURE_NAMES):
        if not races or iterations < 1 or not math.isfinite(regularization) or regularization <= 0 or not math.isfinite(learning_rate) or learning_rate <= 0:
            raise ValueError('training races and positive optimizer settings required')
        if tuple(feature_names) not in (FEATURE_NAMES, ENRICHED_FEATURE_NAMES):
            raise ValueError('unsupported feature schema')
        self.feature_names = tuple(feature_names)
        for r in races: check_training_race(r,self.feature_names)
        ids = [r['race_id'] for r in races]
        if len(set(ids)) != len(ids): raise ValueError('duplicate training race')
        x = np.asarray([f['values'] for r in races for f in r['features']])
        self.mean=x.mean(axis=0); self.scale=np.maximum(x.std(axis=0),.1)
        d=len(self.feature_names); n=len(races); size=max(len(r['features']) for r in races)
        groups=sorted({g for r in races for g in r['features'][0].get('groups',[r['features'][0]['group']])})
        gids={g:i for i,g in enumerate(groups)}
        memberships=[np.array([gids[g] for g in r['features'][0].get('groups',[r['features'][0]['group']])]) for r in races]
        matrix=np.zeros((n,size,d));mask=np.zeros((n,size),dtype=bool)
        for i,r in enumerate(races):
            k=len(r['features']); matrix[i,:k]=(np.asarray([f['values'] for f in r['features']])-self.mean)/self.scale;mask[i,:k]=True
        # A membership matrix supports course and race-category shrinkage together.
        membership=np.zeros((n,len(groups)))
        for i,gs in enumerate(memberships): membership[i,gs]=1
        weights=np.zeros(d); offsets=np.zeros((len(groups),d)); winners=np.array([r['winner_index'] for r in races])
        for _ in range(iterations):
            coef=weights+membership@offsets
            scores=np.einsum('nkd,nd->nk',matrix,coef)
            scores=np.where(mask,scores,-np.inf);scores-=scores.max(axis=1,keepdims=True)
            probs=np.where(mask,np.exp(np.maximum(scores,-700)),0);probs/=probs.sum(axis=1,keepdims=True)
            probs[np.arange(n),winners]-=1
            delta=np.einsum('nkd,nk->nd',matrix,probs)/n
            weights-=learning_rate*(delta.sum(axis=0)+regularization*weights)
            offsets-=learning_rate*(membership.T@delta+4*regularization*offsets)
        self.weights=weights; self.offsets={g:offsets[i] for g,i in gids.items()}
        self.train_end=max(timestamp(r['result_available_at']) for r in races).isoformat()
        self.training_ids=set(ids);self.temperature=1.;self.calibration_end=None
        return self

    def scores(self, features):
        x = (np.asarray([f['values'] for f in features]) - self.mean) / self.scale
        scores = [v @ (self.weights + sum((self.offsets.get(g, 0) for g in f.get('groups',[f['group']])),0)) for v,f in zip(x,features)]
        return np.asarray(scores)

    def calibrate(self, races, candidates=(.5, .75, 1., 1.5, 2., 3.)):
        if not races or not candidates or any(not math.isfinite(t) or t <= 0 for t in candidates):
            raise ValueError('validation races and positive temperatures required')
        if len({r['race_id'] for r in races}) != len(races):
            raise ValueError('duplicate calibration race')
        for r in races:
            check_training_race(r, self.feature_names)
            if r['race_id'] in self.training_ids or any(timestamp(f['cutoff_timestamp']) <= timestamp(self.train_end) for f in r['features']):
                raise ValueError('calibration must follow training without overlap')
        def loss(t):
            return sum(-math.log(max(softmax(self.scores(r['features']), t)[r['winner_index']], 1e-12)) for r in races) / len(races)
        self.temperature = min(candidates, key=loss)
        self.calibration_end = max(timestamp(r['result_available_at']) for r in races).isoformat()
        return {'temperature': self.temperature, 'validation_races': len(races),
                'before_log_loss': loss(1.), 'after_log_loss': loss(self.temperature)}

    def predict(self, features):
        end = self.calibration_end or self.train_end
        if any(timestamp(f['cutoff_timestamp']) <= timestamp(end) for f in features):
            raise ValueError('prediction cutoff must follow training/calibration labels')
        return softmax(self.scores(features), self.temperature)

    def to_dict(self):
        return {'feature_names': list(self.feature_names), 'mean': self.mean.tolist(),
                'scale': self.scale.tolist(), 'weights': self.weights.tolist(),
                'offsets': {g: v.tolist() for g, v in self.offsets.items()},
                'train_end': self.train_end, 'training_ids': sorted(self.training_ids),
                'temperature': self.temperature, 'calibration_end': self.calibration_end}

    @classmethod
    def from_dict(cls, data, allow_research=False):
        if data.get('research_only') and not allow_research:
            raise ValueError('research-only model cannot be loaded for production prediction')
        if tuple(data['feature_names']) not in (FEATURE_NAMES, ENRICHED_FEATURE_NAMES):
            raise ValueError('model feature schema mismatch')
        m = cls()
        m.feature_names = tuple(data['feature_names'])
        for key in ('mean', 'scale', 'weights'):
            value = np.asarray(data[key], dtype=float)
            if value.shape != (len(m.feature_names),) or not np.isfinite(value).all():
                raise ValueError('invalid model coefficients')
            setattr(m, key, value)
        if np.any(m.scale <= 0) or not math.isfinite(data['temperature']) or data['temperature'] <= 0:
            raise ValueError('invalid scale/temperature')
        m.offsets = {g: np.asarray(w, dtype=float) for g, w in data['offsets'].items()}
        if any(w.shape != m.weights.shape or not np.isfinite(w).all() for w in m.offsets.values()):
            raise ValueError('invalid group coefficients')
        m.train_end = data['train_end']
        m.calibration_end = data['calibration_end']
        m.training_ids = set(data['training_ids'])
        m.temperature = data['temperature']
        timestamp(m.train_end)
        if m.calibration_end and timestamp(m.calibration_end) <= timestamp(m.train_end):
            raise ValueError('invalid calibration interval')
        return m
