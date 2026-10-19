"""Exploratory ticket-event counts for the legacy graded runner predictions.

No odds, stakes, or payout figures are inferred from the source CSV.
The July-September 2026 file is already viewed and is NOT a prospective test.
"""
import argparse
import collections
import csv
import json


def audit(path):
    races = collections.defaultdict(list)
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            races[row["race_id"]].append(row)
    counts = collections.Counter()
    for rows in races.values():
        rank = sorted(rows, key=lambda r: (-float(r["probability"]), int(r["horse_number"])))
        if len(rank) < 8 or sum(row["finish"] == "1" for row in rows) != 1:
            raise ValueError("incomplete graded race")
        top = [int(r["horse_number"]) for r in rank[:3]]
        placed = {int(r["horse_number"]) for r in rows if r["finish"].isdigit() and 1 <= int(r["finish"]) <= 3}
        if len(placed) != 3:
            raise ValueError("only three unique podium finishers are supported")
        counts["races"] += 1
        counts["top1_win"] += rank[0]["finish"] == "1"
        counts["top1_place"] += top[0] in placed
        counts["wide_top1_top2"] += set(top[:2]) <= placed
        counts["wide_any_pair_of_top3"] += len(set(top) & placed) >= 2
        counts["trio_top3"] += set(top) == placed
    return {"sample": "viewed_exploratory_not_independent", "counts": dict(counts),
            "interpretation": "wide_any_pair_of_top3 requires three distinct wide tickets; hit rate is not return on investment"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-predictions", required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.legacy_predictions), ensure_ascii=False, indent=2))

