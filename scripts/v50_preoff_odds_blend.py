"""Time-safe preoff market odds signal and walk-forward weighting for v50.

No post-race final odds may enter future forecasting. Use a separately frozen,
timestamped public *preoff* snapshot with complete race field. Coefficient is
supplied by independent chronological backtest; no performance claims here.
"""
from __future__ import annotations
import argparse, datetime as dt, json, math
from pathlib import Path

def timestamp(value):
    if not isinstance(value,str):raise ValueError("timestamp required")
    t=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
    if t.tzinfo is None:raise ValueError("timezone-aware timestamp required")
    return t

def market_probabilities(horses):
    if len(horses)<3 or len({h["number"] for h in horses})!=len(horses):
        raise ValueError("full numbered roster required")
    odds=[h["odds"] for h in horses]
    if not all(isinstance(x,(int,float)) and math.isfinite(x) and x>1 for x in odds):
        raise ValueError("complete valid decimal win odds required")
    prices=[1/x for x in odds]
    total=sum(prices)
    return {h["number"]:p/total for h,p in zip(horses,prices)}

def combine(model, snapshot, *, alpha, off_at):
    """Geometric pool with market de-vig and strict observation-time cutoff."""
    if not 0<=alpha<=1 or not math.isfinite(alpha):
        raise ValueError("invalid odds alpha")
    off=timestamp(off_at)
    observed=timestamp(snapshot.get("observed_at"))
    if observed>=off:
        raise ValueError("odds observed at or after race off")
    if snapshot.get("phase")!="preoff":
        raise ValueError("non-preoff odds cannot be used")
    if snapshot.get("source_kind")!="observed_public_win_odds":
        raise ValueError("unverified odds source kind")
    horses=snapshot.get("horses")
    if not isinstance(horses,list):raise ValueError("full odds field required")
    mm=market_probabilities(horses)
    roster={h["number"] for h in model["horses"]}
    if roster!=set(mm) or len(roster)!=len(model["horses"]):
        raise ValueError("probabilities and odds roster mismatch")
    p={h["number"]:h["p1"] for h in model["horses"]}
    if abs(sum(p.values())-1)>1e-7 or not all(math.isfinite(v) and v>0 for v in p.values()):
        raise ValueError("model probability mass invalid")
    logits={k:(1-alpha)*math.log(p[k])+alpha*math.log(mm[k]) for k in p}
    offset=max(logits.values())
    e={k:math.exp(v-offset) for k,v in logits.items()}
    z=sum(e.values())
    blended={k:v/z for k,v in e.items()}
    rankings=sorted(blended,key=lambda k:(-blended[k],k))
    return {"schema":"v50-preoff-market-odds-v1",
            "alpha":alpha,"odds_observed_at":observed.isoformat(),
            "off_at":off.isoformat(),
            "odds_input":"strictly_observed_preoff",
            "probability_calibration":"UNVERIFIED_REQUIRES_CHRONOLOGICAL_HOLDOUT",
            "ranking":[{"number":k,"model_p1":p[k],"market_p1_devig":mm[k],
                        "blend_p1":blended[k]} for k in rankings]}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--model",required=True)
    parser.add_argument("--odds",required=True)
    parser.add_argument("--off-at",required=True)
    parser.add_argument("--alpha",required=True,type=float)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    result=combine(json.loads(Path(args.model).read_text()),
        json.loads(Path(args.odds).read_text()),alpha=args.alpha,off_at=args.off_at)
    out=Path(args.output)
    if out.exists():raise FileExistsError("cannot overwrite saved preoff output")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"ranking":result["ranking"][:5]},ensure_ascii=False))

if __name__=="__main__":main()
