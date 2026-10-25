"""Conditional trees with strictly historical and within-field relative inputs."""
import copy
import math
import numpy as np
from boosted_race import tree_predict
from exact_rank_model import fit_tree
from features import timestamp
from fitted_model import check_training_race
from history_rank_model import NAMES as HISTORY_NAMES
from history_blend_model import augment_blend
from ranking_model import top3_labels, joint_distribution, RankModel
from rank_calibration import mix_joint

RELATIVE = ('ability','recent_quality','course_form','distance_form','jockey_form',
            'closing_quality','margin_quality','opponent_quality','horse_jockey_form',
            'history_win_form','history_top2_form','recent_win_form')
NAMES = HISTORY_NAMES + tuple(f'{n}_{suffix}' for n in RELATIVE for suffix in ('field_z','field_percentile'))
EXTRA = ('distance_km','turf','class_level','class_known','field_size')


def relative_values(values):
    x=np.asarray(values,float)
    if x.ndim!=2 or x.shape[1]!=len(HISTORY_NAMES) or len(x)<3 or not np.isfinite(x).all():
        raise ValueError('complete finite historical feature field required')
    columns=[x]
    for name in RELATIVE:
        v=x[:,HISTORY_NAMES.index(name)]
        z=np.clip((v-v.mean())/max(float(v.std()),.05),-5,5)
        # Average tied ranks; no arbitrary horse number enters the learned values.
        percentile=((v[:,None]>v[None,:]).sum(axis=1)+.5*(v[:,None]==v[None,:]).sum(axis=1))/len(v)
        columns.append(np.column_stack((z,percentile)))
    return np.column_stack(columns)


def augment_relative(race,index):
    result=augment_blend(race,index)
    values=relative_values([f['values'] for f in result['features']])
    for f,v in zip(result['features'],values):f['values']=v.tolist()
    return result


def matrix(races):
    rows=[]
    for race in races:
        for f,r in zip(race['features'],race['rows']):
            rows.append(list(f['values'])+[float(r['distance_m'])/1000,float(r['surface']=='turf'),
                float(r.get('class_level') or 0),float(r.get('class_level') is not None),len(race['rows'])])
    x=np.asarray(rows,float)
    if x.ndim!=2 or x.shape[1]!=len(NAMES)+len(EXTRA) or not np.isfinite(x).all():
        raise ValueError('relative feature contract mismatch')
    return x


class RelativeRankTree:
    def fit(self,races,family,depth=2,trees=120,rate=.05,minimum_leaf=250,regularization=20,bins=16):
        if (not races or family not in ('win','shared_top3','stagewise_top3') or depth not in (1,2,3)
            or trees<1 or not 0<rate<=1 or minimum_leaf<2 or regularization<=0 or not 2<=bins<=255):
            raise ValueError('invalid model settings')
        if len({r['race_id'] for r in races})!=len(races):raise ValueError('duplicate training race')
        for r in races:
            check_training_race(r,NAMES)
            if timestamp(r['off_timestamp']).year!=2023:raise ValueError('training restricted to 2023')
        self.family=family;x=matrix(races)
        self.edges=[np.unique(np.quantile(x[:,j],np.arange(1,bins)/bins)).tolist() for j in range(x.shape[1])]
        binned=self.bin(x);sizes=np.array([len(r['rows']) for r in races]);starts=np.r_[0,np.cumsum(sizes)[:-1]]
        labels=np.array([top3_labels(r) for r in races])+starts[:,None]
        stages=1 if family=='win' else 3;heads=3 if family=='stagewise_top3' else 1
        masks=np.ones((stages,len(x)),bool)
        for stage in range(stages):
            for earlier in range(stage):masks[stage,labels[:,earlier]]=False
        scores=np.zeros((heads,len(x)));self.forests=[[] for _ in range(heads)]
        for _ in range(trees):
            gs=np.zeros_like(scores);hs=np.zeros_like(scores)
            for stage in range(stages):
                head=stage if heads==3 else 0
                z=np.where(masks[stage],scores[head],-np.inf);z-=np.repeat(np.maximum.reduceat(z,starts),sizes)
                p=np.where(masks[stage],np.exp(np.maximum(z,-700)),0);p/=np.repeat(np.add.reduceat(p,starts),sizes)
                g=-p.copy();g[labels[:,stage]]+=1
                gs[head]+=g/stages;hs[head]+=p*(1-p)/stages
            for head in range(heads):
                tree=fit_tree(binned,self.edges,gs[head],hs[head],depth,minimum_leaf,regularization,rate)
                self.forests[head].append(tree);scores[head]+=tree_predict(tree,binned)
        self.train_end=max((r['result_available_at'] for r in races),key=timestamp)
        self.calibration_end=None;self.temperature=1.
        return self

    def bin(self,x):
        return np.column_stack([np.searchsorted(e,x[:,j],side='left') for j,e in enumerate(self.edges)]).astype(np.uint8)

    def raw(self,races,enforce_time=True):
        if enforce_time and any(timestamp(f['cutoff_timestamp'])<=timestamp(self.calibration_end or self.train_end)
                                for r in races for f in r['features']):raise ValueError('prediction precedes model labels')
        binned=self.bin(matrix(races))
        scores=np.array([sum((tree_predict(t,binned) for t in forest),np.zeros(len(binned))) for forest in self.forests])
        if len(scores)==1:scores=np.repeat(scores,3,axis=0)
        boundaries=np.cumsum([len(r['rows']) for r in races])[:-1]
        return np.split(scores,boundaries,axis=1)

    def to_dict(self):
        return dict(schema='keiba-relative-rank-tree-v1',feature_names=list(NAMES+EXTRA),family=self.family,
            edges=self.edges,forests=self.forests,train_end=self.train_end,calibration_end=self.calibration_end,
            temperature=self.temperature,research_only=True,live_eligible=False,odds_features=False)

    @classmethod
    def from_dict(cls,d):
        if (d.get('schema')!='keiba-relative-rank-tree-v1' or d.get('feature_names')!=list(NAMES+EXTRA)
            or d.get('research_only') is not True or d.get('live_eligible') is not False or d.get('odds_features') is not False):
            raise ValueError('research artifact required')
        m=cls();m.family=d['family'];m.edges=d['edges'];m.forests=d['forests']
        if m.family not in ('win','shared_top3','stagewise_top3'):raise ValueError('invalid family')
        if len(m.edges)!=len(NAMES+EXTRA) or any(not np.isfinite(e).all() or any(b<=a for a,b in zip(e,e[1:])) for e in m.edges):raise ValueError('invalid bins')
        heads=3 if m.family=='stagewise_top3' else 1
        if len(m.forests)!=heads or any(not f for f in m.forests):raise ValueError('invalid heads')
        def check(t,depth=0):
            if depth>3:raise ValueError('invalid depth')
            if set(t)=={'leaf'}:
                if not math.isfinite(t['leaf']):raise ValueError('invalid leaf')
            elif set(t)=={'feature','bin','left','right'}:
                j,k=t['feature'],t['bin']
                if type(j)!=int or not 0<=j<len(m.edges) or type(k)!=int or not 0<=k<len(m.edges[j]):raise ValueError('invalid split')
                check(t['left'],depth+1);check(t['right'],depth+1)
            else:raise ValueError('invalid tree')
        for forest in m.forests:
            for t in forest:check(t)
        for key in ('train_end','calibration_end','temperature'):setattr(m,key,d[key])
        if not math.isfinite(m.temperature) or m.temperature<=0:raise ValueError('invalid temperature')
        timestamp(m.train_end)
        if m.calibration_end and timestamp(m.calibration_end)<=timestamp(m.train_end):raise ValueError('invalid chronology')
        return m


class RelativeRankBlend:
    def __init__(self,base,specialist,weight,alpha=.1):
        if not isinstance(base,RankModel) or not isinstance(specialist,RelativeRankTree) or not 0<=weight<=1 or not 0<=alpha<1:
            raise ValueError('valid research components required')
        self.base=base;self.specialist=specialist;self.weight=weight;self.alpha=alpha

    def predict_races(self,races,enforce_time=True):
        raw=self.specialist.raw(races,enforce_time)
        out=[]
        for r,s in zip(races,raw):
            legacy=[{**f,'values':f['legacy_values']} for f in r['features']]
            a,qa=mix_joint(*self.base.predict(legacy,enforce_time=enforce_time),self.alpha)
            b,qb=mix_joint(*joint_distribution(s,self.specialist.temperature),self.alpha)
            w=self.weight;out.append(((1-w)*a+w*b,(1-w)*qa+w*qb))
        return out

    def to_dict(self):
        return dict(schema='keiba-relative-rank-blend-v1',base=self.base.to_dict(),specialist=self.specialist.to_dict(),
            weight=self.weight,alpha=self.alpha,research_only=True,live_eligible=False,odds_features=False)

    @classmethod
    def from_dict(cls,d):
        if d.get('schema')!='keiba-relative-rank-blend-v1' or d.get('research_only') is not True or d.get('live_eligible') is not False or d.get('odds_features') is not False:
            raise ValueError('research blend required')
        return cls(RankModel.from_dict(d['base']),RelativeRankTree.from_dict(d['specialist']),d['weight'],d['alpha'])
