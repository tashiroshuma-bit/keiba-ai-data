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

# References are descriptive retrospective cohort frequencies, NOT horse forecasts.
# Source: reports/outsider_top3_history_2025.json (351 verified 2025 races).
OUTSIDER_2025_COHORTS={
    "4-6": {"n":1052,"top3":300,"third":120},
    "7-9": {"n":989,"top3":134,"third":69},
    "10+": {"n":1568,"top3":82,"third":33}
}

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
    ordered_market=sorted(mm,key=lambda k:(-mm[k],k))
    favorite,runnerup=ordered_market[:2]
    favorite_share=mm[favorite]
    gap=mm[favorite]-mm[runnerup]
    # Descriptive risk markers only: historical 2025 bin association is not
    # an optimized classifier, causality, or a calibrated event probability.
    signals={
        "favorite_number":favorite,
        "favorite_market_probability":favorite_share,
        "runnerup_number":runnerup,
        "runnerup_market_probability":mm[runnerup],
        "favorite_vs_second_gap":gap,
        "field_size":len(mm),
        "risk_markers":[flag for flag,condition in [
            ("WEAK_MARKET_FAVORITE_UNDER_20PCT",favorite_share<0.20),
            ("MARKET_FAVORITE_BELOW_30PCT",favorite_share<0.30),
            ("CLOSE_TOP_TWO_GAP_UNDER_3PP",gap<0.03),
            ("LARGE_FIELD_14_PLUS",len(mm)>=14)]
            if condition],
        "interpretation":"HISTORICAL_ASSOCIATIONS_NOT_CALIBRATED",
        "evidence":"reports/nonfavorite_winner_analysis_20261107.json"
    }
    # Rank 4th-market-choice-or-worse by the pre-existing v50 *third*
    # placement probability, not by its win probability or post-race popularity.
    market_rank={number:position for position,number in enumerate(ordered_market,1)}
    outsider_third_candidates=[]
    if all(isinstance(h.get("p2"),(int,float)) and
           isinstance(h.get("p3"),(int,float)) and
           math.isfinite(h["p2"]) and math.isfinite(h["p3"]) and
           0<=h["p2"]<=1 and 0<=h["p3"]<=1
           for h in model["horses"]):
        if any(h["p1"]+h["p2"]+h["p3"]>1+1e-7 for h in model["horses"]):
            raise ValueError("invalid model top-three marginal probabilities")
        for h in model["horses"]:
            number=h["number"]
            rank=market_rank[number]
            if rank>=4:
                band="4-6" if rank<=6 else ("7-9" if rank<=9 else "10+")
                cohort=OUTSIDER_2025_COHORTS[band]
                outsider_third_candidates.append({
                    "number":number,"name":h.get("name"),
                    "popularity_band":band,
                    "historical_2025_group_reference_not_horse_probability":{
                        "sample":cohort["n"],
                        "top3_rate":cohort["top3"]/cohort["n"],
                        "third_place_rate":cohort["third"]/cohort["n"],
                        "source":"reports/outsider_top3_history_2025.json"},
                    "market_rank_preoff":rank,
                    "win_odds_preoff":next(x["odds"] for x in horses if x["number"]==number),
                    "v50_p1":h["p1"],"v50_p2":h["p2"],"v50_p3":h["p3"],
                    "v50_top3_probability":h["p1"]+h["p2"]+h["p3"],
                    "model_minus_market_win_probability":h["p1"]-mm[number],
                    "selection_basis":"v50_p3_descending_only",
                    "evaluation_status":"RESEARCH_RANKING_NOT_CALIBRATED"})
        outsider_third_candidates.sort(key=lambda x:(-x["v50_p3"],
                                                      -x["v50_top3_probability"],
                                                      x["market_rank_preoff"],x["number"]))
    return {"schema":"v50-preoff-market-odds-v1",
            "market_structure":signals,
            "outsider_third_candidates":outsider_third_candidates,
            "outsider_third_scope":"4TH_OR_LOWER_MARKET_RANK_PREOFF",
            "outsider_third_evidence":"reports/outsider_top3_history_2025.json",
            "outsider_third_candidate_policy":"p3 ranking only; rank-band cohort rates descriptive, no bonus",
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
