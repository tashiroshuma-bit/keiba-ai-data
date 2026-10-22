"""Rank-specific past finish features; official identities and cutoff remain required."""
import copy
import datetime as dt
import math
import re
import numpy as np
from ranking_model import NAMES as BASE_NAMES,augment,top3_labels,joint_distribution
from features import timestamp,finish
from fitted_model import check_training_race

NAMES=BASE_NAMES+('history_win_form','history_top2_form','recent_win_form',
                 'year_starts_log','win_form_strength','field_relative_win_form')


def augment_history(race,index):
    clean=copy.deepcopy(race)
    for row in clean['rows']:row['sex_age']=re.sub(r'\(cid:\d+\)','',str(row.get('sex_age') or ''))
    result=augment(clean);values=[]
    for row,feature in zip(result['rows'],result['features']):
        off=timestamp(result['off_timestamp']);cutoff=timestamp(feature['cutoff_timestamp'])
        past=index.prior('horse',row['horse_id'],result['race_id'],off,cutoff)
        valid=[x for x in past if finish(x) or x.get('runner_status')=='nonfinisher']
        recent=valid[-3:];n=len(valid)
        wins=sum(finish(x)==1 for x in valid);top2=sum(finish(x) in (1,2) for x in valid)
        annual=sum(timestamp(x['off_timestamp'])>=off-dt.timedelta(days=365) for x in valid)
        values.append([(wins+1)/(n+10),(top2+2)/(n+10),
                       (sum(finish(x)==1 for x in recent)+.5)/(len(recent)+5),
                       math.log1p(annual)/5,n/(n+10)])
    win=np.array([v[0] for v in values]);relative=(win-win.mean())/max(float(win.std()),.05)
    for feature,value,rel in zip(result['features'],values,relative):feature['values']+=value+[float(rel)]
    return result


class HistoryRankModel:
    def fit(self, races, family='shared_top3', regularization=.2, iterations=500, learning_rate=.08):
        if (family not in ('win', 'shared_top3', 'stagewise_top3') or not races or
                not math.isfinite(regularization) or regularization <= 0 or
                not isinstance(iterations, int) or iterations < 1 or
                not math.isfinite(learning_rate) or learning_rate <= 0):
            raise ValueError('valid model settings required')
        if any(timestamp(r['off_timestamp']).year != 2023 for r in races):
            raise ValueError('training restricted to 2023')
        if len({r['race_id'] for r in races}) != len(races):
            raise ValueError('duplicate training race')
        for r in races:
            check_training_race(r, NAMES)
            top3_labels(r)
        x = np.array([f['values'] for r in races for f in r['features']])
        self.mean = x.mean(axis=0); self.scale = np.maximum(x.std(axis=0), .1)
        self.family = family; self.regularization = regularization
        groups = sorted({g for r in races for g in r['features'][0].get('groups', [r['features'][0]['group']])})
        n = len(races); size = max(len(r['features']) for r in races); d = len(NAMES)
        matrix = np.zeros((n, size, d)); mask = np.zeros((n, size), bool)
        membership = np.zeros((n, len(groups)))
        labels = np.array([top3_labels(r) for r in races])
        for i, r in enumerate(races):
            k = len(r['features']); matrix[i, :k] = (np.array([f['values'] for f in r['features']]) - self.mean) / self.scale
            mask[i, :k] = True
            for g in r['features'][0].get('groups', [r['features'][0]['group']]):
                membership[i, groups.index(g)] = 1
        stages = 1 if family == 'win' else 3
        masks = np.tile(mask, (stages, 1, 1))
        for stage in range(stages):
            for earlier in range(stage):
                masks[stage, np.arange(n), labels[:, earlier]] = False
        coefficients = 3 if family == 'stagewise_top3' else 1
        weights = np.zeros((coefficients, d)); offsets = np.zeros((coefficients, len(groups), d))
        for _ in range(iterations):
            gw = np.zeros_like(weights); go = np.zeros_like(offsets)
            for stage in range(stages):
                ci = stage if coefficients == 3 else 0
                scores = np.einsum('nkd,nd->nk', matrix, weights[ci] + membership @ offsets[ci])
                scores = np.where(masks[stage], scores, -np.inf); scores -= scores.max(axis=1, keepdims=True)
                p = np.where(masks[stage], np.exp(np.maximum(scores, -700)), 0); p /= p.sum(axis=1, keepdims=True)
                p[np.arange(n), labels[:, stage]] -= 1
                delta = np.einsum('nkd,nk->nd', matrix, p) / (n * stages)
                gw[ci] += delta.sum(axis=0); go[ci] += membership.T @ delta
            weights -= learning_rate * (gw + regularization * weights)
            offsets -= learning_rate * (go + 4 * regularization * offsets)
        self.weights = weights; self.offsets = {g: offsets[:, i] for i, g in enumerate(groups)}
        self.train_end = max(timestamp(r['result_available_at']) for r in races).isoformat()
        self.calibration_end = None; self.temperature = 1.
        return self

    def scores(self, features):
        x = np.asarray([f['values'] for f in features], float)
        if x.shape != (len(features), len(NAMES)) or not np.isfinite(x).all():
            raise ValueError('rank feature schema mismatch')
        x = (x - self.mean) / self.scale
        out = []
        for v, f in zip(x, features):
            coef = self.weights + sum((self.offsets.get(g, 0) for g in f.get('groups', [f['group']])), 0)
            out.append(coef @ v)
        s = np.asarray(out).T
        return np.repeat(s, 3, axis=0) if s.shape[0] == 1 else s

    def predict(self, features, enforce_time=True):
        if enforce_time and any(timestamp(f['cutoff_timestamp']) <= timestamp(self.calibration_end or self.train_end) for f in features):
            raise ValueError('prediction cutoff must follow training/calibration labels')
        return joint_distribution(self.scores(features), self.temperature)

    def to_dict(self):
        return dict(schema='keiba-history-rank-model-v1', feature_names=list(NAMES), family=self.family,
                    mean=self.mean.tolist(), scale=self.scale.tolist(), weights=self.weights.tolist(),
                    offsets={g: v.tolist() for g, v in self.offsets.items()}, temperature=self.temperature,
                    regularization=self.regularization, train_end=self.train_end, calibration_end=self.calibration_end,
                    research_only=True, live_eligible=False, odds_features=False)

    @classmethod
    def from_dict(cls, data):
        if (data.get('schema') != 'keiba-history-rank-model-v1' or data.get('feature_names') != list(NAMES)
                or data.get('research_only') is not True or data.get('live_eligible') is not False
                or data.get('odds_features') is not False):
            raise ValueError('rank research artifact required')
        m = cls(); m.family = data['family']
        if m.family not in ('win', 'shared_top3', 'stagewise_top3'):
            raise ValueError('invalid rank family')
        count = 3 if m.family == 'stagewise_top3' else 1
        for key, shape in (('mean', (len(NAMES),)), ('scale', (len(NAMES),)), ('weights', (count, len(NAMES)))):
            a = np.asarray(data[key], float)
            if a.shape != shape or not np.isfinite(a).all():
                raise ValueError('invalid rank coefficients')
            setattr(m, key, a)
        m.offsets = {g: np.asarray(v, float) for g, v in data['offsets'].items()}
        if (np.any(m.scale <= 0) or any(v.shape != m.weights.shape or not np.isfinite(v).all() for v in m.offsets.values())
                or not math.isfinite(data['temperature']) or data['temperature'] <= 0):
            raise ValueError('invalid rank scale/temperature')
        for key in ('temperature', 'regularization', 'train_end', 'calibration_end'):
            setattr(m, key, data[key])
        timestamp(m.train_end)
        if m.calibration_end and timestamp(m.calibration_end) <= timestamp(m.train_end):
            raise ValueError('invalid rank time boundary')
        return m
