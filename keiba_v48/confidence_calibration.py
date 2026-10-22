"""Probability-only shrinkage by raw top-label confidence, with joint coherence."""
import math
import numpy as np
from rank_calibration import validate_artifact


def alpha_for(data,marginal,model_sha256,selection_sha256):
    if (data.get('schema')!='keiba-rank-confidence-calibration-v1'
            or data.get('model_sha256')!=model_sha256
            or data.get('base_selection_sha256')!=selection_sha256
            or data.get('research_only') is not True or data.get('selection_year')!=2024):
        raise ValueError('confidence correction differs from frozen model/selection')
    bands=data.get('bands',[]);last=0
    for band in bands:
        lo,hi,a=band['lower'],band['upper'],band['alpha']
        if (lo!=last or not math.isfinite(hi) or hi<=lo or isinstance(a,bool)
                or not math.isfinite(a) or not 0<=a<1):raise ValueError('invalid confidence bands')
        last=hi
    if not bands or last<=1:raise ValueError('confidence bands must cover probability one')
    value=float(np.asarray(marginal)[:,0].max())
    return next(b['alpha'] for b in bands if b['lower']<=value<b['upper'])
