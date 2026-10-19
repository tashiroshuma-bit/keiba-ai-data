"""Post-race market-anchored residual model. Prohibited for live prediction.

The final market supplies a probability prior. Historical features learn only
its residual, rather than claiming a small structural score can price the
entire long-odds tail. Hyperparameters are selected on 2024 only.
"""
import math
import numpy as np
from features import ENRICHED_FEATURE_NAMES,timestamp
from fitted_model import check_training_race,softmax


def market_log(rows):
    odds=np.asarray([r['final_win_odds'] for r in rows],dtype=float)
    if len(odds)<3 or not np.isfinite(odds).all() or (odds<1).any():raise ValueError('full valid final odds required')
    log=-np.log(odds)
    return log-log.max()


class MarketResidualModel:
    def fit(self,races,regularization=.2,iterations=400,learning_rate=.08):
        if not races or regularization<=0 or not math.isfinite(regularization) or iterations<1:raise ValueError('valid training settings required')
        if len({r['race_id'] for r in races})!=len(races):raise ValueError('duplicate race')
        for r in races:check_training_race(r,ENRICHED_FEATURE_NAMES);market_log(r['rows'])
        values=np.array([f['values'] for r in races for f in r['features']]);self.mean=values.mean(axis=0);self.scale=np.maximum(values.std(axis=0),.1)
        n=len(races);k=max(len(r['features']) for r in races);d=len(ENRICHED_FEATURE_NAMES)
        x=np.zeros((n,k,d));base=np.full((n,k),-np.inf);mask=np.zeros((n,k),dtype=bool)
        for i,r in enumerate(races):
            m=len(r['features']);x[i,:m]=(np.array([f['values'] for f in r['features']])-self.mean)/self.scale;base[i,:m]=market_log(r['rows']);mask[i,:m]=True
        weights=np.zeros(d);winner=np.array([r['winner_index'] for r in races])
        for _ in range(iterations):
            scores=base+np.einsum('nkd,d->nk',x,weights);scores-=scores.max(axis=1,keepdims=True)
            p=np.where(mask,np.exp(np.maximum(scores,-700)),0);p/=p.sum(axis=1,keepdims=True);p[np.arange(n),winner]-=1
            weights-=learning_rate*(np.einsum('nkd,nk->d',x,p)/n+regularization*weights)
        self.weights=weights;self.train_end=max(timestamp(r['result_available_at']) for r in races).isoformat();self.training_ids={r['race_id'] for r in races}
        self.calibration_end=None;self.residual_scale=1.;self.market_power=1.;self.regularization=regularization
        return self

    def residual(self,features):
        x=np.asarray([f['values'] for f in features],dtype=float)
        if x.shape!=(len(features),len(ENRICHED_FEATURE_NAMES)) or not np.isfinite(x).all():raise ValueError('feature schema mismatch')
        return ((x-self.mean)/self.scale)@self.weights

    def probabilities(self,race,scale=None,power=None,enforce_time=True):
        if enforce_time and any(timestamp(f['cutoff_timestamp'])<=timestamp(self.calibration_end or self.train_end) for f in race['features']):raise ValueError('evaluation precedes training/calibration labels')
        return softmax((self.market_power if power is None else power)*market_log(race['rows'])+(self.residual_scale if scale is None else scale)*self.residual(race['features']))

    def calibrate(self,races,scales=(0,.25,.5,1),powers=(1,1.1,1.2,1.3)):
        if not races or any(r['race_id'] in self.training_ids or any(timestamp(f['cutoff_timestamp'])<=timestamp(self.train_end) for f in r['features']) for r in races):raise ValueError('calibration must follow training')
        n=len(races);k=max(len(r['features']) for r in races);base=np.zeros((n,k));residual=np.zeros((n,k));mask=np.zeros((n,k),dtype=bool)
        winner=np.array([r['winner_index'] for r in races])
        for i,r in enumerate(races):
            m=len(r['features']);base[i,:m]=market_log(r['rows']);residual[i,:m]=self.residual(r['features']);mask[i,:m]=True
        grid=[]
        for scale in scales:
            for power in powers:
                if not math.isfinite(scale) or not 0<=scale<=1 or not math.isfinite(power) or power<=0:raise ValueError('invalid market calibration')
                score=np.where(mask,power*base+scale*residual,-np.inf);score-=score.max(axis=1,keepdims=True)
                p=np.where(mask,np.exp(np.maximum(score,-700)),0);p/=p.sum(axis=1,keepdims=True)
                loss=-np.log(np.maximum(p[np.arange(n),winner],1e-12)).mean()
                grid.append(dict(residual_scale=scale,market_power=power,log_loss=float(loss)))
        choice=min(grid,key=lambda d:(d['log_loss'],d['residual_scale'],d['market_power']))
        self.residual_scale=choice['residual_scale'];self.market_power=choice['market_power'];self.calibration_end=max(timestamp(r['result_available_at']) for r in races).isoformat()
        return dict(choice=choice,grid=grid,calibration_races=n)

    def to_dict(self):
        return dict(model_type='post_race_market_residual',feature_names=list(ENRICHED_FEATURE_NAMES),mean=self.mean.tolist(),scale=self.scale.tolist(),weights=self.weights.tolist(),
                    train_end=self.train_end,training_ids=sorted(self.training_ids),calibration_end=self.calibration_end,residual_scale=self.residual_scale,market_power=self.market_power,
                    regularization=self.regularization,research_only=True,odds_basis='post_race_final',live_eligible=False)

    @classmethod
    def from_dict(cls,artifact,allow_research=False):
        if not allow_research or artifact.get('model_type')!='post_race_market_residual' or artifact.get('live_eligible') is not False:raise ValueError('explicit post-race research loading required')
        if artifact.get('feature_names')!=list(ENRICHED_FEATURE_NAMES):raise ValueError('schema mismatch')
        m=cls()
        for key in ('mean','scale','weights'):
            a=np.asarray(artifact[key],dtype=float)
            if a.shape!=(23,) or not np.isfinite(a).all():raise ValueError('invalid model arrays')
            setattr(m,key,a)
        if (m.scale<=0).any():raise ValueError('invalid model scale')
        for key in ('train_end','calibration_end','residual_scale','market_power','regularization'):setattr(m,key,artifact[key])
        if not 0<=m.residual_scale<=1 or not math.isfinite(m.market_power) or m.market_power<=0:raise ValueError('invalid calibration')
        timestamp(m.train_end)
        if not m.calibration_end or timestamp(m.calibration_end)<=timestamp(m.train_end):raise ValueError('invalid calibration end')
        m.training_ids=set(artifact['training_ids']);return m
