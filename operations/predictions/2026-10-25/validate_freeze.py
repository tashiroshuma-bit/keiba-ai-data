#!/usr/bin/env python3
"""Validate the immutable 2026-10-25 four-model research-shadow freeze."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SUMMARY = ROOT / "reports/20261025_four_model_all_probabilities.json"
FULL_TICKETS = {
    track: ROOT / f"reports/20261025_four_model_all_tickets_{track}.json"
    for track in ("tokyo", "kyoto", "niigata")
}
MODELS = ("A", "B", "C", "D")
THRESHOLDS = {"single": 0.40, "quinella": 0.25, "trio": 0.30}
TOLERANCE = 2e-6


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    summary = load_json(SUMMARY)
    full = {}
    for path in FULL_TICKETS.values():
        for race in load_json(path)["races"]:
            if race["race"] in full:
                raise AssertionError(f"duplicate race in ticket files: {race['race']}")
            full[race["race"]] = race

    errors = []
    probability_sum_errors = []
    if len(summary["races"]) != 35:
        errors.append(["race_count", len(summary["races"])])

    for race_row in summary["races"]:
        race = race_row["race"]
        models = race_row["models"]
        if tuple(models) != MODELS:
            errors.append([race, "model_keys", list(models)])
            continue

        reference = sorted(
            (horse["no"], horse["name"]) for horse in models["A"]["horses"]
        )
        if len(reference) != len(set(reference)):
            errors.append([race, "duplicate_runner"])

        for model_name, model in models.items():
            runners = sorted((horse["no"], horse["name"]) for horse in model["horses"])
            if runners != reference:
                errors.append([race, model_name, "runner_set_mismatch"])

            for probability in ("p1", "p2", "p3"):
                total = sum(horse[probability] for horse in model["horses"])
                probability_sum_errors.append(abs(total - 1.0))
                if abs(total - 1.0) > TOLERANCE:
                    errors.append([race, model_name, probability, total])

            for ticket_type, threshold in THRESHOLDS.items():
                selected = model["priority"][ticket_type]
                probabilities = [ticket["p"] for ticket in selected["tickets"]]
                if len(probabilities) != selected["count"]:
                    errors.append([race, model_name, ticket_type, "count"])
                if any(
                    probabilities[index] + 1e-12 < probabilities[index + 1]
                    for index in range(len(probabilities) - 1)
                ):
                    errors.append([race, model_name, ticket_type, "sort"])
                cumulative = sum(probabilities)
                if abs(cumulative - selected["cumulative"]) > TOLERANCE:
                    errors.append([race, model_name, ticket_type, "cumulative"])
                if cumulative + 1e-9 < threshold:
                    errors.append([race, model_name, ticket_type, "below_threshold"])
                if len(probabilities) > 1 and sum(probabilities[:-1]) >= threshold - 1e-9:
                    errors.append([race, model_name, ticket_type, "not_minimal"])

            if race not in full:
                errors.append([race, model_name, "missing_full_ticket_distribution"])
                continue
            for ticket_type in ("quinella", "trio"):
                distribution = full[race]["models"][model_name][ticket_type]
                mass = sum(row[1] for row in distribution)
                probability_sum_errors.append(abs(mass - 1.0))
                if abs(mass - 1.0) > TOLERANCE:
                    errors.append([race, model_name, ticket_type, "mass", mass])

    result = {
        "status": "PASS" if not errors else "FAIL",
        "races": len(summary["races"]),
        "model_races": len(summary["races"]) * len(MODELS),
        "max_probability_sum_error": max(probability_sum_errors),
        "errors": errors,
        "source_sha256": sha256(SUMMARY),
        "reread_json": True,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
