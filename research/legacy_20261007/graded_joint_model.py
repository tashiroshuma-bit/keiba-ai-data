"""Compare a graded-only 2023–2025 archive model against 2026 graded races."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar

from joint_top3_model import (FIELDS, diagnostics, feature_snapshot, loss_grad,
                              races_from_frame, ticket_diagnostics, score)


def load_graded(archive_path, graded_2026_path):
    a = json.loads(Path(archive_path).read_text())
    races = pd.DataFrame(a["races"])[["id", "course", "surface", "distance"]]
    runners = pd.DataFrame(a["runners"])
    runners = runners.merge(races, left_on="race_id", right_on="id", validate="many_to_one")
    archived = runners.rename(columns={"horse_number": "number", "horse_name": "horse",
                                       "finish": "finish_order"})
    archived["race_no"] = 0
    archived["grade"] = "graded"
    recent = pd.read_csv(graded_2026_path)
    recent = recent[recent.date >= "2026-01-01"].copy()
    fields = ["race_id", "date", "course", "race_no", "surface", "distance", "frame",
              "number", "horse", "sex", "age", "finish_order", "status", "grade"]
    d = pd.concat([archived[fields], recent[fields]], ignore_index=True)
    d.date = pd.to_datetime(d.date)
    d = d.sort_values(["date", "race_id", "number"]).reset_index(drop=True)
    d = d.groupby("race_id", sort=False).filter(lambda r: len(r) >= 5
            and r.number.is_unique and all((r.finish_order == i).sum() == 1 for i in (1, 2, 3)))
    assert not d.duplicated(["race_id", "number"]).any()
    return d.reset_index(drop=True)


def main(args):
    raw = load_graded(args.archive, args.recent)
    data = feature_snapshot(raw)
    train = data[data.date < "2025-01-01"]
    cal = data[(data.date >= "2025-01-01") & (data.date < "2026-01-01")]
    test = data[data.date >= "2026-01-01"]
    jul = test[test.date >= "2026-07-01"]
    mu = train[FIELDS].mean().to_numpy(); sd = train[FIELDS].std().replace(0, 1).to_numpy()
    grouped = [races_from_frame(f, mu, sd) for f in (train, cal, test, jul)]
    fitted = minimize(loss_grad, np.zeros(len(FIELDS)), args=(grouped[0],), jac=True,
                      method="L-BFGS-B", options={"maxiter": 250})
    assert fitted.success
    beta = fitted.x
    temp = minimize_scalar(lambda t: diagnostics(grouped[1], beta, t)["ordered_top3_log_loss"],
                           bounds=(.5, 5), method="bounded").x
    output = {"source": args.archive, "n_races": raw.race_id.nunique(),
              "train": diagnostics(grouped[0], beta, temp),
              "calibration": diagnostics(grouped[1], beta, temp),
              "2026_diagnostic": diagnostics(grouped[2], beta, temp),
              "2026_jul_sep_diagnostic": diagnostics(grouped[3], beta, temp),
              "ticket_2026_jul_sep_diagnostic": ticket_diagnostics(grouped[3], beta, temp),
              "validation_status": "historical_diagnostic_only",
              "limits": ["No non-graded history before a graded start; prior runs are grade-only.",
                         "2026 outcomes have been inspected before and are not untouched prospective results.",
                         "No synchronized odds or official payouts for ticket ROI."]}
    model = {"fields": FIELDS, "mean": mu.tolist(), "scale": sd.tolist(),
             "beta": beta.tolist(), "temperature": float(temp),
             "trained_through": "2024-12-31", "calibrated_through": "2025-12-31",
             "validation_status": "historical_diagnostic_only",
             "scope": "graded races with prior graded race history only"}
    Path(args.output).mkdir(parents=True, exist_ok=True)
    (Path(args.output) / "graded_only_model.json").write_text(json.dumps(model, ensure_ascii=False, indent=2))
    (Path(args.output) / "graded_only_diagnostic.json").write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--archive", default="jra_ticket_model_v1/bundle/archive.json")
    p.add_argument("--recent", default="jra_ticket_model_v1/graded_identity_enriched.csv")
    p.add_argument("--output", default="joint_top3_outputs")
    p.add_argument("--entries", help="Official future entries CSV (graded-only scoring)")
    p.add_argument("--model", default="joint_top3_outputs/graded_only_model.json")
    p.add_argument("--out", default="joint_top3_outputs/graded_future_diagnostic.json")
    args = p.parse_args()
    if args.entries:
        score(args, load_graded(args.archive, args.recent))
    else:
        main(args)

