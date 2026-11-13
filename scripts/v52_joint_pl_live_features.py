"""V52: reconstruct a 71-dimensional Joint Top3 PL feature vector from 45
audited pre-off covariates using ONLY stored 2023/24 training statistics.

This adapter is usable in production *only after* a genuinely trained V52
candidate has passed the validation gate and production activation.
"""
from __future__ import annotations

import numpy as np
from scripts.v51_joint_pl_new_statistics import FEATURE_INTERACTIONS

SPLINE_KEYS=(
    "horse_strength_vs_field","horse_days_since",
    "jockey_strength_vs_field","horse_last3_mean_strength",
    "past_race_class_last3","prior_corner4_fraction_last3",
    "jockey_track_surface_distance_residual",
)

def transform_live_features(raw45,manifest):
    """Transform without fitting any statistics on the live race.

    Raw input names are exactly the 31+14 research feature names/order.
    Return finite matrix of shape n_runner x n_model_features.
    """
    values=np.asarray(raw45,dtype=np.float64)
    names=manifest["input_names"]
    basis_names=manifest["basis_names"]
    if values.ndim!=2 or values.shape[1]!=45:
        raise ValueError("V52 requires 45 full raw preoff features per runner")
    if len(names)!=45 or len(set(names))!=45:
        raise ValueError("V52 trained raw feature schema is invalid")
    if not np.isfinite(values).all():
        raise ValueError("nonfinite or missing V52 preoff raw feature")
    mu=np.asarray(manifest["raw_feature_mean"],dtype=np.float64)
    sd=np.asarray(manifest["raw_feature_scale"],dtype=np.float64)
    bmu=np.asarray(manifest["basis_mean"],dtype=np.float64)
    bsd=np.asarray(manifest["basis_scale"],dtype=np.float64)
    if (mu.shape!=(45,) or sd.shape!=(45,)
        or bmu.shape!=(71,) or bsd.shape!=(71,)
        or len(basis_names)!=71 or
        not all(np.isfinite(x).all() for x in (mu,sd,bmu,bsd))
        or np.any(sd<=0) or np.any(bsd<=0)):
        raise ValueError("V52 trained normalizer missing or invalid")
    z=np.clip((values-mu)/sd,-7,7)
    basis=[z]
    generated=list(names)
    for key in SPLINE_KEYS:
        if key not in names:raise ValueError("V52 spline feature schema mismatch")
        col=z[:,names.index(key)]
        for knot in (-.5,.5):
            basis.append(np.maximum(0,col-knot)[:,None])
            generated.append(f"spline:{key}:gt{knot}")
    for key1,key2 in FEATURE_INTERACTIONS:
        if key1 not in names or key2 not in names:
            raise ValueError("V52 interaction feature schema mismatch")
        value=z[:,names.index(key1)]*z[:,names.index(key2)]
        basis.append(np.clip(value,-9,9)[:,None])
        generated.append(f"interaction:{key1}*{key2}")
    if generated!=list(basis_names):
        raise ValueError("V52 ordered basis feature names differ from fit")
    x=np.column_stack(basis)
    if x.shape[1]!=71:raise ValueError("V52 expected 71 features")
    result=np.clip((x-bmu)/bsd,-7,7)
    if not np.isfinite(result).all():
        raise ValueError("nonfinite transformed V52 feature")
    return result
