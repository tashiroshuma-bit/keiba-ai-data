"""Leakage-safe promotion gate: no retroactive calibration or promotion.

Only a future frozen preoff forecast with subsequently authenticated results
can count as an independent promotion observation.
"""
import argparse
import json
from pathlib import Path


def assess(records, *, min_races=100):
    valid=[]
    rejected=[]
    for i,r in enumerate(records):
        reasons=[]
        if not r.get("preoff_frozen_sha256"):
            reasons.append("missing_preoff_hash")
        if not r.get("preoff_observed_before_off"):
            reasons.append("not_proven_preoff")
        if not r.get("official_result_verified"):
            reasons.append("unverified_result")
        if not r.get("model_frozen_before_result"):
            reasons.append("not_forward_frozen")
        if not r.get("v49_p1") or not r.get("v50_p1"):
            reasons.append("missing_paired_probabilities")
        if not r.get("actual_winner_number"):
            reasons.append("missing_winner")
        if reasons:
            rejected.append({"index":i,"reasons":reasons})
        else:
            valid.append(r)
    passed=len(valid)>=min_races
    return {"promotion_eligible":passed,
            "eligible_forward_races":len(valid),
            "required_forward_races":min_races,
            "rejected":rejected,
            "status":"ready_for_independent_calibration" if passed else "blocked_insufficient_independent_forward_data",
            "active_version":"v49"}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--records",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    target=Path(a.output)
    if target.exists():
        raise FileExistsError("immutable report exists")
    source=json.loads(Path(a.records).read_text())
    report=assess(source["records"])
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    if not report["promotion_eligible"]:
        raise SystemExit(2)


if __name__=="__main__":
    main()
