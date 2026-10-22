"""A coherent uniform-joint mixture; all existing rank decisions are preserved."""
import math
import numpy as np


def validate_artifact(data, model_sha256, selection_sha256):
    if (data.get('schema') != 'keiba-rank-uniform-joint-calibration-v1'
            or data.get('model_sha256') != model_sha256
            or data.get('base_selection_sha256') != selection_sha256
            or data.get('research_only') is not True
            or data.get('selection_year') != 2024):
        raise ValueError('calibration must match frozen model and selection')
    alpha = data.get('alpha')
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not math.isfinite(alpha) or not 0 <= alpha < 1:
        raise ValueError('invalid joint mixture weight')
    return float(alpha)


def mix_joint(marginal, joint, alpha):
    p = np.asarray(marginal, float); q = np.asarray(joint, float)
    n = len(p)
    if (not math.isfinite(alpha) or not 0 <= alpha < 1 or p.shape != (n, 3)
            or n < 3 or q.shape != (n, n, n) or not np.isfinite(q).all()
            or np.any(q < 0) or not np.isclose(q.sum(), 1)):
        raise ValueError('valid complete rank distribution required')
    i, j, k = np.indices(q.shape)
    valid = (i != j) & (i != k) & (j != k)
    expected = np.column_stack((q.sum(axis=(1, 2)), q.sum(axis=(0, 2)), q.sum(axis=(0, 1))))
    if np.any(q[~valid] != 0) or not np.allclose(p, expected, atol=1e-12, rtol=0):
        raise ValueError('incoherent rank distribution')
    return (1-alpha)*p + alpha/n, (1-alpha)*q + alpha*valid/(n*(n-1)*(n-2))
