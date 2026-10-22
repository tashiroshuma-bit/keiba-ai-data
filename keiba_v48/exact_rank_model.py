"""Exact-set decisions and structural conditional Newton rank trees."""
import itertools
import math
import numpy as np
from boosted_race import tree_predict
from features import timestamp
from ranking_model import NAMES, joint_distribution, top3_labels
from fitted_model import check_training_race

EXTRA = ('distance_km', 'turf', 'class_level', 'class_known', 'field_size')


def exact_set(joint, numbers):
    q = np.asarray(joint, float); n = len(numbers)
    if q.shape != (n,n,n) or n < 3 or not np.isfinite(q).all() or (q < 0).any() or abs(q.sum()-1) > 1e-9:
        raise ValueError('normalized complete joint distribution required')
    if len(set(numbers)) != n:
        raise ValueError('unique horse numbers required')
    combinations = list(itertools.combinations(range(n), 3))
    masses = [sum(q[ix] for ix in itertools.permutations(c)) for c in combinations]
    i = min(range(len(combinations)), key=lambda k:(-masses[k], tuple(sorted(int(numbers[j]) for j in combinations[k]))))
    return list(combinations[i]), float(masses[i])


def matrix(races):
    rows = []
    for race in races:
        for f, r in zip(race['features'], race['rows']):
            rows.append(list(f['values']) + [float(r['distance_m'])/1000, float(r['surface']=='turf'),
                       float(r.get('class_level') or 0), float(r.get('class_level') is not None), len(race['rows'])])
    x = np.asarray(rows, float)
    if x.ndim != 2 or x.shape[1] != len(NAMES)+len(EXTRA) or not np.isfinite(x).all():
        raise ValueError('rank tree feature schema mismatch')
    return x


def fit_tree(binned, edges, gradient, hessian, depth, minimum_leaf, regularization, rate):
    def build(ix, remaining):
        g=gradient[ix].sum(); h=hessian[ix].sum()
        leaf=float(np.clip(g/(h+regularization),-2,2)*rate)
        if remaining==0 or len(ix)<2*minimum_leaf:
            return {'leaf':leaf}
        best=None; gain=g*g/(h+regularization)
        for j, thresholds in enumerate(edges):
            size=len(thresholds)+1
            counts=np.bincount(binned[ix,j],minlength=size).cumsum()[:-1]
            gs=np.bincount(binned[ix,j],weights=gradient[ix],minlength=size).cumsum()[:-1]
            hs=np.bincount(binned[ix,j],weights=hessian[ix],minlength=size).cumsum()[:-1]
            gains=gs*gs/(hs+regularization)+(g-gs)**2/(h-hs+regularization)
            valid=(counts>=minimum_leaf)&(len(ix)-counts>=minimum_leaf)
            gains=np.where(valid,gains,-np.inf)
            if len(gains) and gains.max()>gain+1e-10:
                k=int(gains.argmax()); gain=float(gains[k]); best=(j,k)
        if best is None:
            return {'leaf':leaf}
        j,k=best; left=binned[ix,j]<=k
        return dict(feature=j,bin=k,left=build(ix[left],remaining-1),right=build(ix[~left],remaining-1))
    return build(np.arange(len(binned)),depth)


class ExactRankTree:
    def fit(self,races,family,depth=2,trees=120,rate=.05,minimum_leaf=250,regularization=20,bins=16):
        if (not races or family not in ('win','shared_top3','stagewise_top3') or depth not in (1,2,3)
                or trees<1 or not 0<rate<=1 or minimum_leaf<2 or regularization<=0 or not 2<=bins<=255):
            raise ValueError('invalid conditional rank tree settings')
        if len({r['race_id'] for r in races}) != len(races):
            raise ValueError('duplicate training races')
        for r in races:
            check_training_race(r,NAMES)
            if timestamp(r['off_timestamp']).year!=2023:
                raise ValueError('training restricted to 2023')
        self.family=family; x=matrix(races)
        self.edges=[np.unique(np.quantile(x[:,j],np.arange(1,bins)/bins)).tolist() for j in range(x.shape[1])]
        binned=self.bin(x); sizes=np.asarray([len(r['rows']) for r in races]); starts=np.r_[0,np.cumsum(sizes)[:-1]]
        labels=np.asarray([top3_labels(r) for r in races])+starts[:,None]
        stages=1 if family=='win' else 3; heads=3 if family=='stagewise_top3' else 1
        masks=np.ones((stages,len(x)),bool)
        for stage in range(stages):
            for earlier in range(stage):masks[stage,labels[:,earlier]]=False
        scores=np.zeros((heads,len(x))); self.forests=[[] for _ in range(heads)]
        for _ in range(trees):
            gs=np.zeros_like(scores); hs=np.zeros_like(scores)
            for stage in range(stages):
                head=stage if heads==3 else 0
                z=np.where(masks[stage],scores[head],-np.inf)
                z-=np.repeat(np.maximum.reduceat(z,starts),sizes)
                p=np.where(masks[stage],np.exp(np.maximum(z,-700)),0)
                p/=np.repeat(np.add.reduceat(p,starts),sizes)
                g=-p.copy(); g[labels[:,stage]]+=1
                gs[head]+=g/stages; hs[head]+=p*(1-p)/stages
            for head in range(heads):
                tree=fit_tree(binned,self.edges,gs[head],hs[head],depth,minimum_leaf,regularization,rate)
                self.forests[head].append(tree); scores[head]+=tree_predict(tree,binned)
        self.train_end=max(timestamp(r['result_available_at']) for r in races).isoformat()
        self.calibration_end=None; self.temperature=1.
        return self

    def bin(self,x):
        return np.column_stack([np.searchsorted(e,x[:,j],side='left') for j,e in enumerate(self.edges)]).astype(np.uint8)

    def raw(self,races,enforce_time=True):
        if enforce_time and any(timestamp(f['cutoff_timestamp'])<=timestamp(self.calibration_end or self.train_end) for r in races for f in r['features']):
            raise ValueError('prediction must follow training/calibration')
        binned=self.bin(matrix(races)); out=np.zeros((3,len(binned)))
        for stage in range(3):
            forest=self.forests[stage if len(self.forests)==3 else 0]
            for tree in forest:out[stage]+=tree_predict(tree,binned)
        sizes=[len(r['rows']) for r in races]
        return list(np.split(out,np.cumsum(sizes)[:-1],axis=1))

    def to_dict(self):
        return dict(schema='keiba-exact-rank-trees-v1',family=self.family,feature_names=list(NAMES+EXTRA),
                    edges=self.edges,forests=self.forests,temperature=self.temperature,train_end=self.train_end,
                    calibration_end=self.calibration_end,research_only=True,live_eligible=False,odds_features=False)

    @classmethod
    def from_dict(cls,d):
        if (d.get('schema')!='keiba-exact-rank-trees-v1' or d.get('feature_names')!=list(NAMES+EXTRA)
                or d.get('family') not in ('win','shared_top3','stagewise_top3') or d.get('research_only') is not True
                or d.get('live_eligible') is not False or d.get('odds_features') is not False):
            raise ValueError('exact rank research artifact required')
        m=cls(); m.family=d['family'];m.edges=d['edges'];m.forests=d['forests']
        if len(m.edges)!=len(NAMES+EXTRA) or len(m.forests)!=(3 if m.family=='stagewise_top3' else 1):
            raise ValueError('invalid exact rank dimensions')
        for e in m.edges:
            if len(e)>254 or not np.isfinite(e).all() or (np.diff(e)<=0).any():raise ValueError('invalid bin edges')
        def check(t,depth=0):
            if depth>3:raise ValueError('invalid tree depth')
            if set(t)=={'leaf'}:
                if not math.isfinite(t['leaf']):raise ValueError('invalid leaf')
            elif set(t)=={'feature','bin','left','right'}:
                j=t['feature'];k=t['bin']
                if type(j)!=int or not 0<=j<len(m.edges) or type(k)!=int or not 0<=k<len(m.edges[j]):raise ValueError('invalid split')
                check(t['left'],depth+1);check(t['right'],depth+1)
            else:raise ValueError('invalid tree node')
        for forest in m.forests:
            if not forest:raise ValueError('empty forest')
            for t in forest:check(t)
        for key in ('train_end','calibration_end','temperature'):setattr(m,key,d[key])
        if not math.isfinite(m.temperature) or m.temperature<=0:raise ValueError('invalid temperature')
        timestamp(m.train_end)
        if m.calibration_end and timestamp(m.calibration_end)<=timestamp(m.train_end):raise ValueError('invalid chronology')
        return m
