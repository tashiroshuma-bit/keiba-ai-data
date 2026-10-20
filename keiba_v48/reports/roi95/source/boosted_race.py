"""Small serializable Newton trees trained with race-conditional log loss.

No result columns enter the feature matrix. Final market anchoring is an
explicit research-only family; these artifacts are never live eligible.
"""
import math
import numpy as np
from features import ENRICHED_FEATURE_NAMES, timestamp
from fitted_model import check_training_race

EXTRA = ('age', 'female', 'distance_km', 'turf', 'class_level',
         'class_known', 'history_observed', 'jockey_missing')
MARKET = ('log_final_odds', 'market_probability', 'market_rank_fraction')


def matrix(races, family):
    if family not in ('structural', 'final_market_residual'):
        raise ValueError('unsupported family')
    x = []; base = []; sizes = []
    for race in races:
        sizes.append(len(race['rows']))
        if len(race['features']) != sizes[-1]:
            raise ValueError('full aligned field required')
        odds = None
        if family == 'final_market_residual':
            odds = np.asarray([r['final_win_odds'] for r in race['rows']], float)
            if not np.isfinite(odds).all() or (odds < 1).any():
                raise ValueError('valid complete final odds required')
            prior = 1 / odds; prior /= prior.sum()
            rank = np.argsort(np.argsort(odds, kind='stable'), kind='stable')
        for i, (f, r) in enumerate(zip(race['features'], race['rows'])):
            level = r.get('class_level')
            v = list(f['values']) + [float(r.get('age') or 0),
                float(r.get('sex') in ('牝', 'female', 'F')),
                float(r['distance_m']) / 1000, float(r['surface'] in ('芝', 'turf')),
                float(level or 0), float(level is not None),
                float(f['history_starts'] > 0), float(f['jockey_identity_missing'])]
            if odds is not None:
                v += [math.log(odds[i]), float(prior[i]), float(rank[i]) / max(1, len(odds)-1)]
            x.append(v); base.append(math.log(prior[i]) if odds is not None else 0.)
    values = np.asarray(x, float)
    if not np.isfinite(values).all():
        raise ValueError('non-finite feature')
    return values, np.asarray(base), np.asarray(sizes, int)


def probabilities(scores, sizes, temperature=1.):
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError('positive temperature required')
    starts = np.r_[0, np.cumsum(sizes)[:-1]]
    z = scores / temperature
    z -= np.repeat(np.maximum.reduceat(z, starts), sizes)
    p = np.exp(np.maximum(z, -700))
    p /= np.repeat(np.add.reduceat(p, starts), sizes)
    return p


def tree_predict(tree, binned):
    out = np.empty(len(binned))
    def visit(node, ix):
        if 'leaf' in node:
            out[ix] = node['leaf']; return
        left = binned[ix, node['feature']] <= node['bin']
        visit(node['left'], ix[left]); visit(node['right'], ix[~left])
    visit(tree, np.arange(len(binned)))
    return out


class BoostedRaceModel:
    def fit(self, races, family, depth=2, trees=150, learning_rate=.05,
            minimum_leaf=250, leaf_regularization=20, bins=16):
        if not races or depth not in (1, 2, 3) or trees < 1 or not 0 < learning_rate <= 1 or minimum_leaf < 2 or leaf_regularization <= 0 or not 2 <= bins <= 255:
            raise ValueError('invalid training settings')
        if len({r['race_id'] for r in races}) != len(races):
            raise ValueError('duplicate race')
        for r in races:
            check_training_race(r, ENRICHED_FEATURE_NAMES)
            if timestamp(r['off_timestamp']).year != 2023:
                raise ValueError('training uses 2023 only')
        self.family = family
        self.feature_names = list(ENRICHED_FEATURE_NAMES + EXTRA + (MARKET if family == 'final_market_residual' else ()))
        x, scores, sizes = matrix(races, family)
        self.edges = [np.unique(np.quantile(x[:, j], np.arange(1, bins)/bins)).tolist() for j in range(x.shape[1])]
        binned = self.bin(x)
        starts = np.r_[0, np.cumsum(sizes)[:-1]]
        winner = starts + np.asarray([r['winner_index'] for r in races])
        self.trees = []; self.temperature = 1.
        for _ in range(trees):
            p = probabilities(scores.copy(), sizes)
            gradient = -p.copy(); gradient[winner] += 1
            hessian = p * (1-p)
            def build(ix, remaining):
                g = gradient[ix].sum(); h = hessian[ix].sum()
                leaf = float(np.clip(g/(h+leaf_regularization), -2, 2) * learning_rate)
                if remaining == 0 or len(ix) < 2*minimum_leaf:
                    return {'leaf': leaf}
                best = None; gain = g*g/(h+leaf_regularization)
                for j, edges in enumerate(self.edges):
                    n = len(edges)+1
                    counts = np.bincount(binned[ix, j], minlength=n).cumsum()[:-1]
                    gs = np.bincount(binned[ix, j], weights=gradient[ix], minlength=n).cumsum()[:-1]
                    hs = np.bincount(binned[ix, j], weights=hessian[ix], minlength=n).cumsum()[:-1]
                    valid = (counts >= minimum_leaf) & (len(ix)-counts >= minimum_leaf)
                    gains = gs*gs/(hs+leaf_regularization)+(g-gs)**2/(h-hs+leaf_regularization)
                    gains = np.where(valid, gains, -np.inf)
                    if len(gains) and gains.max() > gain+1e-10:
                        k = int(gains.argmax()); gain = float(gains[k]); best = (j, k)
                if best is None:
                    return {'leaf': leaf}
                j, k = best; left = binned[ix, j] <= k
                return dict(feature=j, bin=k, left=build(ix[left], remaining-1), right=build(ix[~left], remaining-1))
            tree = build(np.arange(len(x)), depth)
            self.trees.append(tree); scores += tree_predict(tree, binned)
        self.train_end = max(timestamp(r['result_available_at']) for r in races).isoformat()
        self.training_ids = sorted(r['race_id'] for r in races)
        self.calibration_end = None
        return self

    def bin(self, x):
        return np.column_stack([np.searchsorted(e, x[:, j], side='left') for j, e in enumerate(self.edges)]).astype(np.uint8)

    def predict(self, races, enforce_time=True):
        end = timestamp(self.calibration_end or self.train_end)
        if enforce_time and any(timestamp(f['cutoff_timestamp']) <= end for r in races for f in r['features']):
            raise ValueError('prediction must follow training/calibration')
        x, scores, sizes = matrix(races, self.family)
        binned = self.bin(x)
        for tree in self.trees:
            scores += tree_predict(tree, binned)
        p = probabilities(scores, sizes, self.temperature)
        return [v.tolist() for v in np.split(p, np.cumsum(sizes)[:-1])]

    def calibrate(self, races, temperatures):
        if not races or any(timestamp(r['off_timestamp']).year != 2024 or r['race_id'] in self.training_ids for r in races):
            raise ValueError('calibration uses disjoint 2024 only')
        raw = self.predict(races); grid = []
        for t in temperatures:
            ps = [probabilities(np.log(np.maximum(p, 1e-300)), [len(p)], t) for p in raw]
            loss = float(np.mean([-math.log(max(p[r['winner_index']], 1e-12)) for p, r in zip(ps, races)]))
            grid.append(dict(temperature=t, log_loss=loss))
        best = min(grid, key=lambda g: (g['log_loss'], abs(g['temperature']-1)))
        self.temperature = best['temperature']
        self.calibration_end = max(timestamp(r['result_available_at']) for r in races).isoformat()
        return dict(selected=best, grid=grid)

    def to_dict(self):
        return dict(model_type='boosted_race_research', research_only=True, live_eligible=False,
                    odds_basis='post_race_final' if self.family == 'final_market_residual' else 'no_current_odds',
                    family=self.family, feature_names=self.feature_names, edges=self.edges,
                    trees=self.trees, temperature=self.temperature, train_end=self.train_end,
                    calibration_end=self.calibration_end, training_ids=self.training_ids)

    @classmethod
    def from_dict(cls, artifact, allow_research=False):
        if not allow_research or artifact.get('model_type') != 'boosted_race_research' or artifact.get('live_eligible') is not False or artifact.get('research_only') is not True:
            raise ValueError('explicit research-only loading required')
        m = cls(); m.family = artifact['family']
        if m.family not in ('structural', 'final_market_residual'):
            raise ValueError('invalid model family')
        expected = list(ENRICHED_FEATURE_NAMES + EXTRA + (MARKET if m.family == 'final_market_residual' else ()))
        if artifact['feature_names'] != expected or len(artifact['edges']) != len(expected):
            raise ValueError('feature schema mismatch')
        m.feature_names = expected; m.edges = artifact['edges']
        for edges in m.edges:
            a = np.asarray(edges, float)
            if a.ndim != 1 or len(a) > 254 or not np.isfinite(a).all() or (np.diff(a) <= 0).any():
                raise ValueError('invalid bin edges')
        def validate(node, depth=0):
            if depth > 3:
                raise ValueError('invalid tree depth')
            if set(node) == {'leaf'}:
                if not math.isfinite(node['leaf']):
                    raise ValueError('invalid leaf')
                return
            if set(node) != {'feature','bin','left','right'}:
                raise ValueError('invalid tree node')
            j = node['feature']; k = node['bin']
            if type(j) is not int or not 0 <= j < len(expected) or type(k) is not int or not 0 <= k < len(m.edges[j]):
                raise ValueError('invalid split')
            validate(node['left'],depth+1); validate(node['right'],depth+1)
        m.trees = artifact['trees']
        if not m.trees:
            raise ValueError('empty model')
        for tree in m.trees:validate(tree)
        m.temperature = artifact['temperature']
        if not math.isfinite(m.temperature) or m.temperature <= 0:
            raise ValueError('invalid temperature')
        m.train_end = artifact['train_end']; m.calibration_end = artifact['calibration_end']
        if timestamp(m.train_end).year != 2023 or (m.calibration_end and timestamp(m.calibration_end) <= timestamp(m.train_end)):
            raise ValueError('invalid model chronology')
        m.training_ids = artifact['training_ids']
        if len(set(m.training_ids)) != len(m.training_ids):
            raise ValueError('duplicate training IDs')
        return m
