"""Reproduce real V51 best-race selective-ranking hit rates from saved holdout.

This is a *coverage / accuracy* audit, not training and not an improvement
in full-field winner picks. Only the 2025 and 2026 real full-ID validation
summaries are accepted; 2026 is never used to fit a threshold or coefficients.
"""
import argparse
import json
import math
from pathlib import Path

DEFAULT_INPUT=Path(__file__).resolve().parents[1]/"reports/v51_recovered_ids_cal2025_heldout2026.json"
THRESHOLDS=(0.30,0.40,0.50)
EXPECTED={2025:(2925,719),2026:(2411,603)}

def _bins(doc,year):
    entry=doc["modes"]["full"][f"{year}_calibrated_on_2025"]
    bins=entry["calibration_reliability"]["confidence"]
    n, hits=EXPECTED[year]
    if entry["n_races"]!=n or entry["top1_hits"]!=hits:
        raise ValueError("unexpected official V51 full-ID holdout cohort")
    if sum(b["n"] for b in bins)!=n:
        raise ValueError("missing confidence strata")
    counts=[]
    for item in bins:
        ni=int(item["n"])
        observed=float(item["observed_hit"])
        k=round(ni*observed)
        if ni<0 or not 0<=k<=ni or abs(k/ni-observed)>1e-10:
            raise ValueError("bin accuracy does not represent integral race hits")
        counts.append((float(item["bin"]),ni,k,
                       float(item["mean_pred_confidence"])))
    if sum(row[2] for row in counts)!=hits:
        raise ValueError("race winner totals do not reconcile")
    return counts

def _threshold(counts,minimum):
    chosen=[row for row in counts
            if row[0]>minimum+1e-9]
    n=sum(x[1] for x in chosen)
    hits=sum(x[2] for x in chosen)
    total=sum(x[1] for x in counts)
    if not n:raise ValueError("confidence threshold produces zero sample")
    return {
        "minimum_top1_probability":minimum,
        "races":n,"winner_hits":hits,
        "coverage_of_all_races":n/total,
        "winner_hit_rate_selected_only":hits/n,
        "mean_forecast_confidence":sum(x[1]*x[3] for x in chosen)/n,
        "mean_confidence_minus_observed_hit_rate":sum(x[1]*x[3] for x in chosen)/n-hits/n,
        "not_full_race_model_accuracy":True,
    }

def audit(doc):
    output={"schema":"jra-v51-selective-winner-ranking-audit-v1",
        "model":"v51","comparison":"same v51 model across confidence cutoffs",
        "source":"reports/v51_recovered_ids_cal2025_heldout2026.json",
        "reported_only_from_previously_saved_real_holdout":True,
        "not_a_coefficient_refit":True,
        "not_full_population_rank_improvement":True,
        "thresholds_predeclared_without_2026_optimization":list(THRESHOLDS),
        "years":{}}
    for year in (2025,2026):
        x=doc["modes"]["full"][f"{year}_calibrated_on_2025"]
        bins=_bins(doc,year)
        output["years"][str(year)]={
            "races":x["n_races"],"winner_hits":x["top1_hits"],
            "all_races_winner_hit_rate":x["top1_accuracy"],
            "selected_race_thresholds":[_threshold(bins,v) for v in THRESHOLDS],
        }
    output["limitations"]=[
        "Selective accuracy increases when low-confidence races are omitted; accuracy on all races remains unchanged.",
        "2025 temperatures were fitted on 2025, so 2025 probabilities are not independently calibrated.",
        "2026 is a previously inspected retrospective holdout, not a prospective future-season trial.",
        "Selection threshold data are aggregate confidence bins, not per-race frozen production picks.",
        "No future pre-off source authenticity can be inferred from historical result dates."
    ]
    return output

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",default=str(DEFAULT_INPUT))
    p.add_argument("--output")
    a=p.parse_args()
    result=audit(json.loads(Path(a.input).read_text(encoding="utf-8")))
    serialized=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if a.output:
        out=Path(a.output)
        out.parent.mkdir(parents=True,exist_ok=True)
        with out.open("x",encoding="utf-8") as f:f.write(serialized)
    print(serialized)

if __name__=="__main__":
    main()
