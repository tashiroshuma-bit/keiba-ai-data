"""v4.8 prototype. Only pre-race features permitted. No fitted weights claimed."""
import numpy as np

def market_probs(odds):
    o=np.asarray(odds,dtype=float)
    if np.any(o<=1): raise ValueError('invalid odds')
    w=1/o
    return w/w.sum()

def win_probs(odds, pre_race_scores=None, alpha=0.0):
    base=market_probs(odds)
    s=np.zeros(len(base)) if pre_race_scores is None else np.asarray(pre_race_scores,dtype=float)
    if len(s)!=len(base): raise ValueError('length mismatch')
    logits=np.log(base)+alpha*(s-s.mean())
    p=np.exp(logits-logits.max()); return p/p.sum()

def podium_probabilities(p):
    """Plackett-Luce ordering: approximate P(1st), P(2nd), P(3rd), and pair/triple probability."""
    p=np.asarray(p,dtype=float); n=len(p)
    first=p.copy(); second=np.zeros(n); third=np.zeros(n)
    for i in range(n):
      for j in range(n):
        if j==i: continue
        pij=p[i]*p[j]/(1-p[i]); second[j]+=pij
        for k in range(n):
          if k==i or k==j: continue
          third[k]+=pij*p[k]/(1-p[i]-p[j])
    return np.stack([first,second,third],axis=1)

def evaluate_bets(probability,decimal_odds):
    return {'hit_probability':float(probability),'expected_return_per_yen':float(probability*decimal_odds),'expected_profit_per_yen':float(probability*decimal_odds-1)}

if __name__=='__main__':
    odds=[1.5,7.9,11,14.5,23.4]
    p=win_probs(odds)
    x=podium_probabilities(p)
    print('Demonstration only, truncated 5-horse field; not a historical backtest')
    print('win',p.round(4),'column totals',x.sum(axis=0))
