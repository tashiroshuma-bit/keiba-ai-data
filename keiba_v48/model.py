"""v4.8 prototype. Only pre-race features permitted. No fitted weights claimed."""
import numpy as np

def market_probs(odds):
    o=np.asarray(odds,dtype=float)
    if o.ndim!=1 or len(o)<2 or not np.isfinite(o).all() or np.any(o<=1): raise ValueError('invalid odds')
    w=1/o
    return w/w.sum()

def win_probs(odds, pre_race_scores=None, alpha=0.0):
    base=market_probs(odds)
    s=np.zeros(len(base)) if pre_race_scores is None else np.asarray(pre_race_scores,dtype=float)
    if s.shape!=base.shape or not np.isfinite(s).all() or not np.isfinite(alpha): raise ValueError('invalid scores or length mismatch')
    logits=np.log(base)+alpha*(s-s.mean())
    p=np.exp(logits-logits.max()); return p/p.sum()

def podium_probabilities(p):
    """Plackett-Luce ordering: approximate P(1st), P(2nd), P(3rd), and pair/triple probability."""
    from backtest_engine import podium
    p=np.asarray(p,dtype=float)
    if p.ndim!=1 or len(p)<3 or not np.isfinite(p).all() or np.any(p<=0) or abs(p.sum()-1)>1e-9:
        raise ValueError('positive normalized complete field required')
    return np.asarray(podium(p.tolist())[0])

def evaluate_bets(probability,decimal_odds):
    return {'hit_probability':float(probability),'expected_return_per_yen':float(probability*decimal_odds),'expected_profit_per_yen':float(probability*decimal_odds-1)}

if __name__=='__main__':
    odds=[1.5,7.9,11,14.5,23.4]
    p=win_probs(odds)
    x=podium_probabilities(p)
    print('Demonstration only, truncated 5-horse field; not a historical backtest')
    print('win',p.round(4),'column totals',x.sum(axis=0))
