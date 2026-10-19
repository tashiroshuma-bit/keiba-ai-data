"""Experimental race-level Plackett-Luce top-three model.

Training uses only earlier completed starts in a local historical snapshot.
No odds, finish, popularity or same-race result is used as a feature.
"""
import argparse
import collections
import datetime as dt
import json
import math
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar

SOURCE = "source_packages/jra_graded_identity_jockey_validation_2026.zip"
FIELDS = ["age_scaled", "female", "frame_fraction", "horse_fraction", "history_starts",
          "history_win_rate", "history_top3_rate", "recent_top3", "recent_finish",
          "course_starts", "course_top3_rate", "distance_starts", "distance_top3_rate",
          "layoff_log", "debut", "history_missing"]


def normalize_name(name):
    return re.sub(r"\s+", "", str(name)).replace("・", "")


def horse_key(row):
    name = normalize_name(row["horse"])
    year = int(str(row["date"])[:4]) - int(row["age"])
    return (name, year)


def load_snapshot(path=SOURCE):
    with zipfile.ZipFile(path) as z:
        raw = pd.read_csv(z.open("full_non_graded_results_identity_v2.csv"))
    graded = pd.read_csv("jra_ticket_model_v1/graded_identity_enriched.csv")
    fields = ["race_id", "date", "course", "race_no", "surface", "distance", "frame",
              "number", "horse", "sex", "age", "finish_order", "status", "grade"]
    raw = pd.concat([raw[fields], graded[fields]], ignore_index=True)
    assert raw.race_id.notna().all() and raw.number.notna().all()
    raw["date"] = pd.to_datetime(raw.date)
    raw = raw.sort_values(["date", "race_id", "number"]).reset_index(drop=True)
    races = raw.groupby("race_id", sort=False)
    eligible = races.filter(lambda r: len(r) >= 5 and len(r.number.unique()) == len(r)
                            and all((r.finish_order == k).sum() == 1 for k in (1, 2, 3)))
    excluded = raw.race_id.nunique() - eligible.race_id.nunique()
    if excluded > 1:
        raise ValueError(f"unexpected incomplete races: {excluded}")
    raw = eligible.reset_index(drop=True)
    assert not raw.duplicated(["race_id", "number"]).any()
    return raw


def state_features(row, state, field_size):
    key = horse_key(row)
    h = state.get(key, [])
    prior = [r for r in h if r["date"] < row["date"]]
    n = len(prior)
    course = [r for r in prior if r["course"] == row["course"]]
    dist = [r for r in prior if r["surface"] == row["surface"]
            and abs(r["distance"] - row["distance"]) <= 200]
    # Shrink empirical rates so one prior win is not treated as certainty.
    rate = lambda rows, pred, alpha: (sum(pred(r) for r in rows) + alpha) / (len(rows) + 4)
    recent = sorted(prior, key=lambda r: r["date"], reverse=True)[:3]
    gap = (row["date"] - recent[0]["date"]).days if recent else 120
    sex = str(row["sex"])
    return np.array([
        (float(row["age"]) - 4) / 4, float(sex in ("牝", "f", "F")),
        (float(row["frame"]) - 1) / 7, (float(row["number"]) - 1) / max(1, field_size - 1),
        math.log1p(n), rate(prior, lambda r: r["finish"] == 1, .25),
        rate(prior, lambda r: r["finish"] <= 3, .75),
        rate(recent, lambda r: r["finish"] <= 3, .75),
        np.mean([min(18, r["finish"]) for r in recent]) / 18 if recent else .5,
        math.log1p(len(course)), rate(course, lambda r: r["finish"] <= 3, .75),
        math.log1p(len(dist)), rate(dist, lambda r: r["finish"] <= 3, .75),
        math.log1p(max(1, min(gap, 730))) / math.log(731),
        float(n == 0), float(n == 0),
    ], dtype=float)


def update_state(state, race):
    for _, r in race.iterrows():
        state[horse_key(r)].append({"date": r.date, "course": r.course,
                                   "surface": r.surface, "distance": r.distance,
                                   "finish": r.finish_order if pd.notna(r.finish_order) else 99})


def feature_snapshot(raw):
    state = collections.defaultdict(list)
    features = []
    for _, race in raw.groupby("race_id", sort=False):
        features.extend(state_features(r, state, len(race)) for _, r in race.iterrows())
        update_state(state, race)
    out = raw.copy()
    out[FIELDS] = np.vstack(features)
    assert out[FIELDS].notna().all().all()
    return out


def races_from_frame(frame, mean=None, scale=None):
    x = frame[FIELDS].to_numpy(dtype=float)
    if mean is not None:
        x = (x - mean) / scale
    all_races = []
    for _, r in frame.assign(_row=np.arange(len(frame))).groupby("race_id", sort=False):
        idx = r._row.to_numpy()
        pos = [int(np.flatnonzero(r.finish_order.to_numpy() == k)[0]) for k in (1, 2, 3)]
        all_races.append((x[idx], pos, str(r.date.iloc[0].date())))
    return all_races


def top3_logprob(scores, positions):
    # Stable conditional softmax, removing selected runner after each place.
    remain = list(range(len(scores)))
    logp = 0.
    for selected in positions:
        z = scores[remain]
        mx = max(z)
        logp += scores[selected] - mx - math.log(np.exp(z - mx).sum())
        remain.remove(selected)
    return logp


def loss_grad(beta, races, ridge=.05):
    ll, grad = 0., np.zeros_like(beta)
    for x, order, _ in races:
        scores = x @ beta
        remain = list(range(len(scores)))
        for selected in order:
            z = scores[remain]
            w = np.exp(z - z.max())
            p = w / w.sum()
            ll -= scores[selected] - z.max() - math.log(w.sum())
            grad += x[remain].T @ p - x[selected]
            remain.remove(selected)
    return ll / len(races) + ridge * np.dot(beta, beta), grad / len(races) + 2 * ridge * beta


def diagnostics(races, beta, temperature):
    losses, unif, win, top3_hit = [], [], 0, 0
    for x, order, _ in races:
        s = x @ beta / temperature
        losses.append(-top3_logprob(s, order))
        n = len(s)
        unif.append(math.log(n * (n - 1) * (n - 2)))
        win += int(np.argmax(s) == order[0])
        top3_hit += int(np.argmax(s) in order)
    return {"races": len(races), "ordered_top3_log_loss": float(np.mean(losses)),
            "uniform_top3_log_loss": float(np.mean(unif)),
            "top_score_winner_rate": win / len(races),
            "top_score_top3_rate": top3_hit / len(races)}


def ordered_scenarios(runners, scores):
    if len(runners) < 5 or len(runners) != len(set(runners)):
        raise ValueError("field requires 5+ distinct runner numbers")
    weights = np.exp(scores - max(scores))
    total = weights.sum()
    output = []
    for i in range(len(runners)):
        for j in range(len(runners)):
            if i == j: continue
            for k in range(len(runners)):
                if k in (i, j): continue
                p = (weights[i] / total * weights[j] / (total - weights[i])
                     * weights[k] / (total - weights[i] - weights[j]))
                output.append({"order": [int(runners[i]), int(runners[j]), int(runners[k])],
                               "probability": float(p)})
    return output


def ticket_diagnostics(races, beta, temperature):
    """Check predeclared one-wide/one-trio selection rule on each full race."""
    records = {"top2_wide": [], "top3_trio": []}
    for x, actual, _ in races:
        scores = x @ beta / temperature
        picks = list(np.argsort(-scores)[:3])
        scenarios = ordered_scenarios(list(range(len(scores))), scores)
        for event, selected in (("top2_wide", set(picks[:2])),
                                ("top3_trio", set(picks))):
            p = sum(row["probability"] for row in scenarios
                    if selected.issubset(set(row["order"])))
            y = int(selected.issubset(set(actual)))
            records[event].append((p, y))
    return {event: {"count": len(rows), "predicted_mean": float(np.mean([r[0] for r in rows])),
                    "observed_rate": float(np.mean([r[1] for r in rows])),
                    "brier": float(np.mean([(p-y)**2 for p, y in rows]))}
            for event, rows in records.items()}


def fit(args):
    raw = load_snapshot(args.source)
    d = feature_snapshot(raw)
    train = d[d.date < "2026-04-01"].copy()
    cal = d[(d.date >= "2026-04-01") & (d.date < "2026-07-01")].copy()
    test = d[(d.date >= "2026-07-01") & (d.date < "2026-10-01")].copy()
    mu = train[FIELDS].mean().to_numpy(); sd = train[FIELDS].std().replace(0, 1).to_numpy()
    groups = [races_from_frame(f, mu, sd) for f in (train, cal, test)]
    assert all(groups), "chronological partitions missing"
    result = minimize(loss_grad, np.zeros(len(FIELDS)), args=(groups[0],), jac=True,
                      method="L-BFGS-B", options={"maxiter": 250})
    assert result.success, result.message
    beta = result.x
    obj = lambda t: diagnostics(groups[1], beta, t)["ordered_top3_log_loss"]
    temperature = minimize_scalar(obj, bounds=(.5, 5), method="bounded").x
    subsets = {"graded": test[test.grade == "graded"],
               "two_year_old": test.groupby("race_id").filter(lambda r: (r.age == 2).all()),
               "two_year_old_graded": test[(test.age == 2) & (test.grade == "graded")]}
    metrics = {"data": {"source": args.source, "n_rows": len(raw),
                         "n_races": raw.race_id.nunique(),
                         "identity": "horse name plus inferred birth year; verified IDs not assumed",
                         "data_start": str(raw.date.min().date()), "data_end": str(raw.date.max().date())},
               "splits": {"train": ["2025-10-04", "2026-03-31"],
                          "calibration": ["2026-04-01", "2026-06-30"],
                          "diagnostic_holdout": ["2026-07-01", "2026-09-30"]},
               "temperature": float(temperature),
               "train": diagnostics(groups[0], beta, temperature),
               "calibration": diagnostics(groups[1], beta, temperature),
               "diagnostic_holdout": diagnostics(groups[2], beta, temperature),
               "diagnostic_segments": {name: diagnostics(races_from_frame(rows, mu, sd), beta, temperature)
                                       for name, rows in subsets.items() if not rows.empty},
               "ticket_diagnostics": {"calibration": ticket_diagnostics(groups[1], beta, temperature),
                                      "historical_holdout": ticket_diagnostics(groups[2], beta, temperature),
                                      "graded_historical_holdout": ticket_diagnostics(
                                          races_from_frame(subsets["graded"], mu, sd), beta, temperature)},
               "validation_status": "historical_diagnostic_only",
               "limitations": ["Existing 2026 results were inspected during model development; test is not untouched prospective validation.",
                               "No historical synchronized odds or official payout archive for ticket-level ROI.",
                               "Horse identity uses name plus inferred birth year; collisions and missing history are possible.",
                               "Recent historical snapshot begins 2025-10; earlier careers are left censored."]}
    model = {"fields": FIELDS, "mean": mu.tolist(), "scale": sd.tolist(),
             "beta": beta.tolist(), "temperature": float(temperature),
             "trained_through": "2026-03-31", "calibrated_through": "2026-06-30",
             "validation_status": "historical_diagnostic_only"}
    Path(args.output).mkdir(parents=True, exist_ok=True)
    (Path(args.output) / "joint_top3_model.json").write_text(json.dumps(model, ensure_ascii=False, indent=2))
    (Path(args.output) / "joint_top3_diagnostic.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


def score(args, raw=None):
    model = json.loads(Path(args.model).read_text())
    if model["validation_status"] != "historical_diagnostic_only":
        raise ValueError("unknown model validation state")
    raw = load_snapshot(args.source) if raw is None else raw
    entries = pd.read_csv(args.entries)
    if "horse_name" in entries.columns and "horse" not in entries.columns:
        entries = entries.rename(columns={"horse_name": "horse"})
    required = {"race_id", "date", "course", "surface", "distance", "frame", "number",
                "horse", "sex", "age", "source_url"}
    if not required.issubset(entries.columns) or entries[list(required)].isna().any().any():
        raise ValueError(f"entries require complete official pre-race fields: {sorted(required)}")
    if len(entries.race_id.unique()) != 1 or len(entries) < 5 or entries.number.duplicated().any():
        raise ValueError("one complete race with 5+ unique horse numbers required")
    if entries.date.nunique() != 1 or entries.date.iloc[0] <= str(raw.date.max().date()):
        raise ValueError("prospective race date must postdate historical snapshot")
    if not entries.source_url.astype(str).str.startswith("https://www.jra.go.jp/").all():
        raise ValueError("official JRA entries source required")
    if {"finish_order", "winner", "top3", "popularity"} & set(entries.columns):
        raise ValueError("entries contain outcome or market fields")
    entries["date"] = pd.to_datetime(entries.date)
    state = collections.defaultdict(list)
    for _, race in raw.groupby("race_id", sort=False):
        update_state(state, race)
    x = np.vstack([state_features(r, state, len(entries)) for _, r in entries.iterrows()])
    scores = (x - np.asarray(model["mean"])) / np.asarray(model["scale"])
    scores = scores @ np.asarray(model["beta"]) / model["temperature"]
    runners = entries.number.astype(int).tolist()
    scenarios = ordered_scenarios(runners, scores)
    winner = {n: 0. for n in runners}
    top3 = {n: 0. for n in runners}
    for item in scenarios:
        winner[item["order"][0]] += item["probability"]
        for number in item["order"]:
            top3[number] += item["probability"]
    output = {"race_id": entries.race_id.iloc[0],
              "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "validation_status": "historical_diagnostic_only",
              "validation_report_id": "joint_top3_diagnostic.json",
              "entries_source_url": entries.source_url.iloc[0],
              "caveat": "Model scores are historical diagnostics, not calibrated real-world odds or validated ticket EV.",
              "rankings": [{"horse_number": n, "horse": h,
                            "model_win_probability_diagnostic": winner[n],
                            "model_top3_probability_diagnostic": top3[n]}
                           for n, h in zip(runners, entries.horse)],
              "top3": scenarios}
    output["rankings"].sort(key=lambda r: -r["model_win_probability_diagnostic"])
    Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"Wrote {args.out}: {len(scenarios)} exhaustive ordered outcomes; status historical_diagnostic_only")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=SOURCE)
    parser.add_argument("--output", default="joint_top3_outputs")
    parser.add_argument("--model", default="joint_top3_outputs/joint_top3_model.json")
    parser.add_argument("--entries", help="Official complete future starting list CSV (scoring mode)")
    parser.add_argument("--out", default="joint_top3_outputs/future_joint_top3_diagnostic.json")
    args = parser.parse_args()
    score(args) if args.entries else fit(args)

