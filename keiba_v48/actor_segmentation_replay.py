"""Historical condition-segmented actor comparison (research only).

2023 historical rows establish prior features, 2024 may be used for selecting
a rule; 2025/2026 are previously inspected retrospective comparison cohorts.
No production promotion, and no odds/outcomes as predictor inputs.
"""
import argparse
import collections
import gzip
import hashlib
import json
import math
import pickle
from pathlib import Path

from actor_segmentation import segment_actor
from completion_validation import sha
from enriched_features import load_archive
from features import timestamp
from validation import canonical


def index_history(history):
    indexed = {"horse": collections.defaultdict(list),
               "jockey": collections.defaultdict(list)}
    for row in history:
        for kind in indexed:
            ident = row.get(kind + "_id")
            if ident and not str(ident).startswith("unlinked:"):
                indexed[kind][ident].append(row)
    for mapping in indexed.values():
        for rows in mapping.values():
            rows.sort(key=lambda r: (timestamp(r["off_timestamp"]), r["race_id"]))
    return indexed


def actor_signal(rows, cutoff, identity, kind, context):
    # The segmentation module rejects assumed historical publication times.
    # In retrospective lag research, the lag is explicitly declared as an
    # assumption, so convert only that marker for the research calculation.
    past = [dict(r, availability_basis="retrospective_assumed_lag")
            if r.get("availability_basis", "").startswith("assumed_") else r
            for r in rows]
    result = segment_actor(past, cutoff, identity, kind, context)
    groups = ("overall", "same_surface", "same_distance_band",
              "same_track_surface", "recent")
    # Nested condition shrinkage: no division by zero and no fake zero-start win rate.
    components = [result[k] for k in groups]
    weights = (0.10, 0.20, 0.30, 0.25, 0.15)
    numerator = sum(w * c["support"] * (c["win_shrunk"] - .1)
                    for w, c in zip(weights, components) if c["starts"])
    denominator = sum(w * c["support"] for w, c in zip(weights, components))
    return (numerator / denominator if denominator else 0.), result["overall"]["starts"]


def evaluate(db, cache, lag, output):
    from actor_hit_research import hit_record
    from actor_index_replay import index_picks
    root = Path(__file__).resolve().parent
    state = json.loads((root.parent / "PROJECT_STATE.json").read_text())
    dbhash = sha(db)
    if dbhash != state["database"]["sha256"]:
        raise ValueError("canonical database SHA mismatch")
    stored = pickle.loads((Path(cache) / f"features_lag{lag}.pkl").read_bytes())
    if stored["identity"]["db"] != dbhash or stored["identity"]["lag"] != lag:
        raise ValueError("feature cache mismatch")
    reference = {}
    source = root / "reports/evidence_rank"
    for name, proof in json.loads((source / f"prediction_inventory_lag{lag}.json").read_text()).items():
        if sha(source / name) != proof["sha256"]:
            raise ValueError("reference SHA mismatch")
        for r in json.loads(gzip.decompress((source / name).read_bytes())):
            reference[r["race_id"]] = r
    history, _, _ = load_archive(db, lag, allow_unlinked_fields=True)
    indexed = index_history(history)
    rows = []
    for race in sorted((r for r in stored["races"] if r["race_id"] in reference),
                       key=lambda r: (timestamp(r["off_timestamp"]), r["race_id"])):
        prior = reference[race["race_id"]]
        numbers = [int(r["horse_number"]) for r in race["rows"]]
        if numbers != list(map(int, prior["horse_numbers"])):
            raise ValueError("roster mismatch")
        target = list(map(int, prior["candidate"]["target"]))
        cutoff = min(timestamp(f["cutoff_timestamp"]) for f in race["features"])
        signals = {"horse": [], "jockey": []}
        support = {"horse": [], "jockey": []}
        for runner in race["rows"]:
            for kind in signals:
                ident = runner.get(kind + "_id")
                value, count = actor_signal(indexed[kind].get(ident, []), cutoff,
                                            ident, kind, runner)
                signals[kind].append(value)
                support[kind].append(count)
        rules = {
            "horse_conditions": signals["horse"],
            "jockey_conditions": signals["jockey"],
            "horse_jockey_conditions": [
                .35 * h + .65 * j for h, j in zip(signals["horse"], signals["jockey"])
            ],
        }
        forecasts = {}
        for name, values in rules.items():
            order = sorted(range(len(numbers)), key=lambda i: (-values[i], numbers[i]))
            forecasts[name] = int(numbers[order[0]] == target[0])
        forecasts["previous_calibrated"] = int(
            int(prior["candidate"]["winner_pick"]) == target[0])
        rows.append(dict(race_id=race["race_id"], year=race["rows"][0]["race_date"][:4],
                         hits=forecasts, horse_support=support["horse"],
                         jockey_support=support["jockey"]))
    years = {}
    for year in ("2024", "2025", "2026"):
        subset = [r for r in rows if r["year"] == year]
        if not subset:
            continue
        years[year] = dict(races=len(subset), methods={
            key: dict(hits=sum(r["hits"][key] for r in subset),
                      hit_rate=sum(r["hits"][key] for r in subset)/len(subset))
            for key in subset[0]["hits"]},
            horse_coverage=sum(sum(x > 0 for x in r["horse_support"])/len(r["horse_support"])
                               for r in subset)/len(subset),
            jockey_coverage=sum(sum(x > 0 for x in r["jockey_support"])/len(r["jockey_support"])
                                for r in subset)/len(subset))
    report = dict(schema="keiba-actor-segmentation-retrospective-v1",
                  db_sha256=dbhash, lag_days=lag, years=years,
                  rules_predeclared=True, training_new_weights=False,
                  historic_availability="assumed_lag_not_actual_observation",
                  production_promoted=False,
                  caveat="2025/2026 already inspected; no unseen-forward claim")
    Path(output).write_text(canonical(report) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--lag", type=int, choices=(2, 7), required=True)
    parser.add_argument("--output", required=True)
    a = parser.parse_args()
    print(json.dumps(evaluate(a.db, a.cache, a.lag, a.output), ensure_ascii=False))
