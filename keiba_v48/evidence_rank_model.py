"""Runner-level evidence calibration with coherent conditional podium probabilities."""
import math
import numpy as np
from features import timestamp
from ranking_model import RankModel,top3_labels,NAMES
from rank_calibration import mix_joint

EVIDENCE_NAMES=('centered_log_base_p1','no_observed_history','history_strength',
                'log_p1_no_history','log_p1_weak_history','missing_jockey')


def project_beta(beta):
    beta=beta.copy();beta[0]=np.clip(beta[0],-.75,1)
    factor=1.
    for offset in (beta[4],beta[3]+beta[4]):
        if offset>0:factor=min(factor,(1-beta[0])/offset)
        elif offset<0:factor=min(factor,(-.75-beta[0])/offset)
    beta[3:5]*=max(0,factor)
    return beta


def evidence_matrix(features,p1):
    p=np.asarray(p1,float)
    if p.shape!=(len(features),) or (p<=0).any() or not np.isfinite(p).all() or abs(p.sum()-1)>1e-9:
        raise ValueError('normalized positive first-place probabilities required')
    counts=np.array([float(f['history_starts']) for f in features])
    if not np.isfinite(counts).all() or (counts<0).any():raise ValueError('invalid observed history count')
    strength=np.minimum(np.log1p(counts)/math.log(21),1)
    missing=np.array([float(f.get('jockey_identity_missing',f['values'][NAMES.index('jockey_identity_missing')])) for f in features])
    if not np.isfinite(missing).all() or not np.isin(missing,[0,1]).all():raise ValueError('invalid jockey evidence flag')
    logp=np.log(p);logp-=logp.mean();empty=(counts==0).astype(float)
    return np.column_stack((logp,empty,strength,logp*empty,logp*(1-strength),missing))


def corrected_first(p1,x,beta):
    z=np.log(p1)+x@np.asarray(beta,float);z-=z.max()
    p=np.exp(np.maximum(z,-700));return p/p.sum()


def replace_first(p,q,new_first):
    p=np.asarray(p,float);q=np.asarray(q,float);new_first=np.asarray(new_first,float)
    if q.shape!=(len(p),len(p),len(p)) or (new_first<=0).any() or abs(new_first.sum()-1)>1e-9:
        raise ValueError('complete normalized probability distributions required')
    adjusted=q*(new_first/p[:,0])[:,None,None]
    marginal=np.column_stack((adjusted.sum(axis=(1,2)),adjusted.sum(axis=(0,2)),adjusted.sum(axis=(0,1))))
    return marginal,adjusted


class EvidenceRankModel:
    def __init__(self,base,beta,calibration_end,alpha=.1,regularization=None):
        beta=np.asarray(beta,float)
        if not isinstance(base,RankModel) or beta.shape!=(len(EVIDENCE_NAMES),) or not np.isfinite(beta).all():
            raise ValueError('valid base and evidence coefficients required')
        coefficients=np.array([1+beta[0],1+beta[0]+beta[4],1+beta[0]+beta[3]+beta[4]])
        if (coefficients<.25-1e-12).any() or (coefficients>2+1e-12).any() or not math.isfinite(alpha) or not 0<=alpha<1:
            raise ValueError('invalid calibration settings')
        if timestamp(calibration_end)<=timestamp(base.train_end):raise ValueError('calibration must follow training')
        self.base=base;self.beta=beta;self.calibration_end=calibration_end;self.alpha=alpha;self.regularization=regularization

    @classmethod
    def fit(cls,base,races,regularization,iterations=1000,rate=.1,alpha=.1):
        if not races or regularization<=0 or not math.isfinite(regularization) or iterations<1 or not 0<rate<=1:
            raise ValueError('valid calibration data/settings required')
        if len({r['race_id'] for r in races})!=len(races):raise ValueError('duplicate calibration race')
        matrices=[];priors=[];targets=[]
        for race in races:
            off=timestamp(race['off_timestamp'])
            if off.year!=2024 or off.month>6:raise ValueError('evidence fit restricted to 2024 H1')
            if timestamp(race['off_timestamp'])<=timestamp(base.train_end):raise ValueError('calibration precedes base fit')
            features=race['features'];legacy=[{**f,'values':f.get('legacy_values',f['values'])} for f in features]
            p,_=mix_joint(*base.predict(legacy,enforce_time=False),alpha)
            matrices.append(evidence_matrix(features,p[:,0]));priors.append(p[:,0]);targets.append(top3_labels(race)[0])
        beta=np.zeros(len(EVIDENCE_NAMES))
        sizes=np.array([len(p) for p in priors]);starts=np.r_[0,np.cumsum(sizes)[:-1]]
        x=np.vstack(matrices);prior=np.concatenate(priors);labels=np.array(targets)+starts
        for _ in range(iterations):
            z=np.log(prior)+x@beta;z-=np.repeat(np.maximum.reduceat(z,starts),sizes)
            prob=np.exp(np.maximum(z,-700));prob/=np.repeat(np.add.reduceat(prob,starts),sizes)
            prob[labels]-=1
            gradient=x.T@prob/len(races)+regularization*beta
            beta=project_beta(beta-rate*gradient)
        return cls(base,beta,max((r['result_available_at'] for r in races),key=timestamp),alpha,regularization)

    def predict(self,features,enforce_time=True):
        if enforce_time and any(timestamp(f['cutoff_timestamp'])<=timestamp(self.calibration_end) for f in features):
            raise ValueError('prediction must follow evidence calibration')
        legacy=[{**f,'values':f.get('legacy_values',f['values'])} for f in features]
        p,q=mix_joint(*self.base.predict(legacy,enforce_time=enforce_time),self.alpha)
        x=evidence_matrix(features,p[:,0]);new_first=corrected_first(p[:,0],x,self.beta)
        return replace_first(p,q,new_first)

    def to_dict(self):
        return dict(schema='keiba-evidence-rank-model-v1',base=self.base.to_dict(),beta=self.beta.tolist(),
            feature_names=list(EVIDENCE_NAMES),calibration_end=self.calibration_end,alpha=self.alpha,
            regularization=self.regularization,research_only=True,live_eligible=False,odds_features=False)

    @classmethod
    def from_dict(cls,d):
        if d.get('schema')!='keiba-evidence-rank-model-v1' or d.get('feature_names')!=list(EVIDENCE_NAMES) or d.get('research_only') is not True or d.get('live_eligible') is not False or d.get('odds_features') is not False:
            raise ValueError('evidence research artifact required')
        return cls(RankModel.from_dict(d['base']),d['beta'],d['calibration_end'],d['alpha'],d['regularization'])
