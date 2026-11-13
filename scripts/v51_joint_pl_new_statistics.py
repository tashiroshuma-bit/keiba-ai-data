"""V51 research: hierarchical JOINT top-3 Plackett-Luce, nonlinear interactions.

Major statistical architecture change: no scaling the frozen winner
coefficients. Train all three conditional finish positions using a single
coherent penalized likelihood with partial pooling between podium heads.

Zero future-label features, no result-odds or race-day postrace bodyweight.
Research-only: nothing here alters official standard_v51_model.json.
"""
from __future__ import annotations

import math
import numpy as np
from scipy.optimize import minimize

FEATURE_INTERACTIONS=(
    ("horse_strength_vs_field","jockey_strength_vs_field"),
    ("horse_strength_vs_field","field_size"),
    ("horse_last3_mean_strength","horse_strength_vs_field"),
    ("horse_prior_top3_rate","horse_log_starts"),
    ("jockey_track_winrate","jockey_log_starts"),
    ("jockey_surface_winrate","surface_turf"),
    ("past_race_class_last3","horse_strength_vs_field"),
    ("past_rivals_prior_strength_last3","horse_strength_vs_field"),
    ("prior_corner4_fraction_last3","horse_strength_vs_field"),
    ("prior_early_style_last3","field_size"),
    ("jockey_track_surface_distance_residual","jockey_strength_vs_field"),
    ("previous_reported_weight_delta_pct_last3","horse_days_since"),
)

def _zscore_fit_transform(raw,train_rows):
    x=np.asarray(raw,dtype=np.float64)
    if x.ndim!=2 or not np.isfinite(x).all():
        raise ValueError("feature inputs must be rectangular and finite")
    tr=x[train_rows]
    mu=tr.mean(0)
    sd=tr.std(0)
    sd=np.where(sd>1e-8,sd,1.0)
    return np.clip((x-mu)/sd,-7,7),mu,sd

def design_matrix(original,extra,names31,names14,train_rows):
    """Out-of-training-only scalers: 31+14, nonlinear hinges and interactions.

    Nonlinear basis is stable under sample ordering; feature names are explicit.
    No current-race labels or probabilities of the outcome are used.
    """
    x=np.column_stack([original,extra])
    names=list(names31)+list(names14)
    if len(names)!=x.shape[1] or len(set(names))!=len(names):
        raise ValueError("feature name/order mismatch")
    z,mu,sd=_zscore_fit_transform(x,train_rows)
    # ReLU-style 2-knot truncated linear splines on key prior covariates.
    spline_keys=[
        "horse_strength_vs_field","horse_days_since",
        "jockey_strength_vs_field","horse_last3_mean_strength",
        "past_race_class_last3","prior_corner4_fraction_last3",
        "jockey_track_surface_distance_residual",
    ]
    basis=[z]
    basisnames=list(names)
    for k in spline_keys:
        if k not in names:
            raise ValueError("missing splined feature "+k)
        col=z[:,names.index(k)]
        for knot in (-.5,.5):
            basis.append(np.maximum(0,col-knot)[:,None])
            basisnames.append(f"spline:{k}:gt{knot}")
    # Only prior-data covariates; clipped to avoid explosive interactions.
    for a,b in FEATURE_INTERACTIONS:
        if a not in names or b not in names:
            raise ValueError("missing preoff interaction source")
        xx=z[:,names.index(a)]*z[:,names.index(b)]
        basis.append(np.clip(xx,-9,9)[:,None])
        basisnames.append(f"interaction:{a}*{b}")
    rawbasis=np.column_stack(basis)
    transformed,transmu,transsd=_zscore_fit_transform(rawbasis,train_rows)
    receipt={
        "input_names":names,"basis_names":basisnames,
        "raw_feature_mean":mu.tolist(),"raw_feature_scale":sd.tolist(),
        "basis_mean":transmu.tolist(),"basis_scale":transsd.tolist(),
        "train_rows":len(train_rows),"feature_count":len(basisnames),
        "feature_selection_used_labels":False,
    }
    return transformed,receipt

def _samples(groups,stage):
    """Only unambiguous complete top3 rows at each stage."""
    samples=[]
    for g in groups:
        if stage>1 and not g["podium_valid"]:
            continue
        removed=set() if stage==1 else ({int(g["first"])} if stage==2
             else {int(g["first"]),int(g["second"])})
        indices=np.asarray([int(k) for k in g["indices"] if int(k) not in removed],
                           dtype=np.int64)
        target=int(g[("first","second","third")[stage-1]])
        if target not in indices or len(indices)<1:
            raise ValueError("invalid conditional top-three race")
        samples.append((indices,target,g["date"]))
    return samples

def _recency_weights(dates,half_life_days):
    from datetime import date
    days=[date.fromisoformat(s) for s in dates]
    latest=max(days)
    age=np.asarray([(latest-d).days for d in days],dtype=float)
    if half_life_days is None:
        w=np.ones(len(days))
    else:
        if half_life_days<30:raise ValueError("recency half-life too small")
        w=np.exp2(-age/float(half_life_days))
        w=w/w.mean()
    return w

def joint_stage_fit(X,groups,*,ridge=.05,coupling=.10,
                    half_life_days=365,maxiter=180):
    """Joint top3 PL likelihood, with hierarchical stage shrinkage.

    Objective = weighted mean stage-conditional negative log likelihood
      + ridge/2*sum(||w_s||²) + coupling/2 * sum(||w_s-w_1||²), s=2,3.

    The stage-specific PL denominators remove previously selected finishers.
    With 2023/24 strictly prior training races this avoids within-race leakage.
    """
    xx=np.asarray(X,dtype=float)
    if xx.ndim!=2 or not np.isfinite(xx).all() or len(groups)<2:
        raise ValueError("cannot train: no finite training race design")
    if ridge<=0 or coupling<0:raise ValueError("invalid ridge/coupling")
    stages=[]
    for stage in (1,2,3):
        sam=_samples(groups,stage)
        if not sam:raise ValueError("not enough unambiguous training podium")
        lens=np.array([len(q[0]) for q in sam],dtype=np.int64)
        offsets=np.r_[0,np.cumsum(lens)][:-1]
        idx=np.concatenate([q[0] for q in sam])
        target=np.array([q[1] for q in sam],dtype=np.int64)
        weights=_recency_weights([q[2] for q in sam],half_life_days)
        stages.append((xx[idx],xx[target],lens,offsets,weights,len(sam)))
    n_features=xx.shape[1]
    stage_imp=np.array([1.,.7,.5],dtype=float)
    stage_imp=stage_imp/stage_imp.sum()

    def objective(flat):
        w=flat.reshape(3,n_features)
        loss=0.
        grad=np.zeros_like(w)
        for st,(features,chosen,lens,offsets,sw,n) in enumerate(stages):
            scores=features@w[st]
            m=np.maximum.reduceat(scores,offsets)
            shifted=np.exp(scores-np.repeat(m,lens))
            denom=np.add.reduceat(shifted,offsets)
            p=shifted/np.repeat(denom,lens)
            loss+=stage_imp[st]*np.sum(
                sw*(m+np.log(denom)-chosen@w[st]))/n
            wt_p=p*np.repeat(sw,lens)
            grad[st]+=stage_imp[st]*(
                features.T@wt_p-(sw[:,None]*chosen).sum(0))/n

        loss+=.5*ridge*np.sum(w*w)
        grad+=ridge*w
        d=w[1:]-w[0]
        loss+=.5*coupling*np.sum(d*d)
        grad[1:]+=coupling*d
        grad[0]-=coupling*d.sum(0)
        return float(loss),grad.ravel()

    initial=np.zeros((3,n_features),dtype=float)
    opt=minimize(objective,initial.ravel(),jac=True,method="L-BFGS-B",
            options={"maxiter":maxiter,"ftol":1e-9,"maxls":30})
    if not opt.success and np.linalg.norm(opt.jac)>1e-4:
        raise RuntimeError("joint top3 PL optimization failed: "+str(opt.message))
    weights=opt.x.reshape(3,n_features)
    return weights,{
        "model_type":"hierarchical_regularized_top3_plackett_luce",
        "objective":"joint_conditioned_podium_negative_loglikelihood",
        "train_first_races":stages[0][-1],
        "train_complete_podium_races":stages[2][-1],
        "stage_importance":stage_imp.tolist(),
        "ridge":ridge,"coupling":coupling,"half_life_days":half_life_days,
        "iterations":int(opt.nit),"optimizer_success":bool(opt.success),
        "gradient_norm":float(np.linalg.norm(opt.jac)),
        "loss_penalized":float(opt.fun),
        "source_labels_used_to_form_model":True,
        "outcome_labels_used_in_prediction_inputs":False,
    }

def race_score_records(X,groups,coef):
    w=np.asarray(coef,dtype=np.float64)
    if w.shape!=(3,X.shape[1]):raise ValueError("podium coefficient shape mismatch")
    return [([X[g["indices"]]@w[i] for i in range(3)],g) for g in groups]
