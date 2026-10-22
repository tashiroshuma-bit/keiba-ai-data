"""A coherent joint mixture; each task still returns exactly one decision."""
import math
from features import timestamp
from ranking_model import RankModel,augment
from history_rank_model import HistoryRankModel,augment_history
from rank_calibration import mix_joint


def augment_blend(race,index):
    old=augment(race);new=augment_history(race,index)
    for feature,legacy in zip(new['features'],old['features']):feature['legacy_values']=legacy['values']
    return new


class HistoryBlendModel:
    def __init__(self,base,specialist,weight,base_alpha=.1,specialist_alpha=0):
        if (not isinstance(base,RankModel) or not isinstance(specialist,HistoryRankModel)
                or any(isinstance(v,bool) or not math.isfinite(v) for v in (weight,base_alpha,specialist_alpha))
                or not 0<=weight<=1 or not 0<=base_alpha<1 or not 0<=specialist_alpha<1):
            raise ValueError('valid frozen model components and convex mixture required')
        self.base=base;self.specialist=specialist;self.weight=weight
        self.base_alpha=base_alpha;self.specialist_alpha=specialist_alpha
        self.train_end=max((base.train_end,specialist.train_end),key=timestamp)
        self.calibration_end=max((base.calibration_end or base.train_end,
                                  specialist.calibration_end or specialist.train_end),key=timestamp)

    def predict(self,features,enforce_time=True):
        legacy=[]
        for f in features:
            if 'legacy_values' not in f:raise ValueError('legacy feature contract required')
            legacy.append({**f,'values':f['legacy_values']})
        a,qa=mix_joint(*self.base.predict(legacy,enforce_time=enforce_time),self.base_alpha)
        b,qb=mix_joint(*self.specialist.predict(features,enforce_time=enforce_time),self.specialist_alpha)
        w=self.weight;return (1-w)*a+w*b,(1-w)*qa+w*qb

    def to_dict(self):
        return dict(schema='keiba-history-blend-model-v1',base=self.base.to_dict(),specialist=self.specialist.to_dict(),
            weight=self.weight,base_alpha=self.base_alpha,specialist_alpha=self.specialist_alpha,
            research_only=True,live_eligible=False,odds_features=False)

    @classmethod
    def from_dict(cls,data):
        if (data.get('schema')!='keiba-history-blend-model-v1' or data.get('research_only') is not True
                or data.get('live_eligible') is not False or data.get('odds_features') is not False):
            raise ValueError('research-only history mixture required')
        return cls(RankModel.from_dict(data['base']),HistoryRankModel.from_dict(data['specialist']),
                   data['weight'],data['base_alpha'],data['specialist_alpha'])
