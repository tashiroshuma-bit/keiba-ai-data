"""Conditional top-three rank learner; outcome/market fields are never inputs."""
import copy
import itertools
import math
import re
import unicodedata
import numpy as np
from features import ENRICHED_FEATURE_NAMES, timestamp, finish
from fitted_model import check_training_race

NAMES = ENRICHED_FEATURE_NAMES + ('age', 'female', 'gelding', 'age_missing',
                                'horse_identity_missing', 'jockey_identity_missing')


def augment(race):
    result = copy.deepcopy(race)
    for f, row in zip(result['features'], result['rows']):
        text = unicodedata.normalize('NFKC', str(row.get('sex_age') or ''))
        match = re.search(r'\d+', text)
        age = int(match[0]) if match else None
        if age is not None and not 1 <= age <= 30:
            raise ValueError('invalid age')
        f['values'] += [age or 0, float('牝' in text), float('セ' in text), float(age is None),
                        float(bool(row.get('horse_identity_missing'))), float(not row.get('jockey_id'))]
    return result


def top3_labels(race):
    labels = []
    for rank in (1, 2, 3):
        indexes = [i for i, row in enumerate(race['rows']) if finish(row) == rank]
        if len(indexes) != 1:
            raise ValueError('unique top-three ranks required')
        labels.append(indexes[0])
    return labels


def joint_distribution(scores, temperature=1.0):
    s = np.asarray(scores, dtype=float)
    if s.ndim != 2 or s.shape[0] != 3 or s.shape[1] < 3 or not np.isfinite(s).all():
        raise ValueError('three finite full-field score vectors required')
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError('positive temperature required')
    e = np.exp(np.maximum(s / temperature - (s / temperature).max(axis=1, keepdims=True), -300))
    n = s.shape[1]
    # Sum the remaining runners directly to avoid cancellation at extreme scores.
    i, j, k = np.indices((n, n, n))
    valid = (i != j) & (i != k) & (j != k)
    second = np.where(~np.eye(n, dtype=bool), e[1][None, :], 0)
    second /= second.sum(axis=1, keepdims=True)
    third = np.where(valid, e[2][None, None, :], 0)
    denominator = third.sum(axis=2, keepdims=True)
    third = np.divide(third, denominator, out=np.zeros_like(third), where=denominator > 0)
    q = (e[0] / e[0].sum())[:, None, None] * second[:, :, None] * third
    marginal = np.column_stack((q.sum(axis=(1, 2)), q.sum(axis=(0, 2)), q.sum(axis=(0, 1))))
    return marginal, q


def picks(marginal, joint, horse_numbers):
    numbers = list(map(int, horse_numbers))
    n = len(numbers)
    winner = min(range(n), key=lambda i: (-marginal[i, 0], numbers[i]))
    trio = sorted(range(n), key=lambda i: (-sum(marginal[i]), numbers[i]))[:3]
    ordered = min(np.argwhere(joint == joint.max()).tolist(), key=lambda ix: tuple(numbers[i] for i in ix))
    return winner, trio, list(ordered)


class RankModel:
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
        return dict(schema='keiba-rank-model-v1', feature_names=list(NAMES), family=self.family,
                    mean=self.mean.tolist(), scale=self.scale.tolist(), weights=self.weights.tolist(),
                    offsets={g: v.tolist() for g, v in self.offsets.items()}, temperature=self.temperature,
                    regularization=self.regularization, train_end=self.train_end, calibration_end=self.calibration_end,
                    research_only=True, live_eligible=False, odds_features=False)

    @classmethod
    def from_dict(cls, data):
        if (data.get('schema') != 'keiba-rank-model-v1' or data.get('feature_names') != list(NAMES)
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
