"""Research-only retrospective power calibration of frozen per-race win probabilities.

Usage:
 python scripts/compare_win_probability_power.py \
  --predictions reports/odds_refresh_20261101_morning/PREDICTIONS.json \
  --settlement reports/review_20261101/FOUR_MODEL_SETTLEMENT_20261101T194949+0900.md

Never uses the evaluated races to claim unseen performance or promote weights.
"""
import argparse
import json
import math
import re
from pathlib import Path


def winners_from_settlement(text):
    found = {}
    for track, race, first in re.findall(
        r"^- \\[(東京|京都)(\\d+)R\\]\\([^)]+\\)：(\\d+)-\\d+-\\d+",
        text, re.MULTILINE
    ):
        key = f"{track}{race}R"
        if key in found:
            raise ValueError(f"duplicate result: {key}")
        found[key] = int(first)
    return found


def power_normalize(probabilities, exponent):
    if not math.isfinite(exponent) or exponent <= 0:
        raise ValueError("positive exponent required")
    if not probabilities or any(not math.isfinite(p) or p < 0 for p in probabilities):
        raise ValueError("nonnegative finite probabilities required")
    powered = [p ** exponent for p in probabilities]
    total = sum(powered)
    if total <= 0:
        raise ValueError("positive probability mass required")
    return [p / total for p in powered]


def evaluate(races, winners, model, exponent):
    n = hit = 0
    logloss = brier = 0.
    for race in races:
        key = race["race"]
        if key not in winners:
            continue
        horses = race["models"][model]["horses"]
        numbers = [h["number"] for h in horses]
        if len(numbers) != len(set(numbers)) or winners[key] not in numbers:
            raise ValueError(f"invalid field/result: {key}")
        probabilities = power_normalize([h["p1"] for h in horses], exponent)
        actual = numbers.index(winners[key])
        n += 1
        hit += int(max(range(len(numbers)), key=lambda i: probabilities[i]) == actual)
        logloss -= math.log(max(probabilities[actual], 1e-300))
        brier += sum((p - (i == actual)) ** 2 for i, p in enumerate(probabilities))
    if not n:
        raise ValueError("no matching evaluated races")
    return dict(races=n, top1_hits=hit, top1_rate=hit/n, logloss=logloss/n,
                brier=brier/n)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--settlement", required=True)
    args = parser.parse_args()
    races = json.loads(Path(args.predictions).read_text())["races"]
    winners = winners_from_settlement(Path(args.settlement).read_text())
    output = {
        "schema": "research-retrospective-power-calibration-v1",
        "formula": "P_new(i) = P_old(i)^gamma / sum_h P_old(h)^gamma",
        "warning": "Same-period retrospective diagnostic; no out-of-sample claim, no automatic promotion.",
        "results": {
            model: {str(gamma): evaluate(races, winners, model, gamma)
                    for gamma in (0.75, 1.0, 1.25, 1.5, 2.0)}
            for model in "ABCD"
        }
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
