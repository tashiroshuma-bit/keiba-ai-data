"""Audit whether canonical history can support every frozen V51 feature.

No feature value is imputed or substituted. This is a coverage audit, not
a trained-model parity assertion or a future-race forecast.
"""
import argparse
import collections
import json
from pathlib import Path
import sqlite3

FEATURE_SOURCE_FIELDS = {
    "field_size": ("races", "expected_runners"),
    "distance_km": ("races", "distance_m"),
    "surface_turf": ("races", "surface"),
    "age": ("runner_payload", "age"),
    "is_female": ("runner_payload", "sex"),
    "carried_weight": ("runner_payload", "carried_weight"),
    "gate_fraction": ("runner_payload", "gate"),
    "horse_num_fraction": ("runners", "horse_number"),
    "horse_log_starts": ("history", "horse_id"),
    "horse_prior_win_rate": ("history_payload", "finish_position"),
    "horse_prior_top3_rate": ("history_payload", "finish_position"),
    "horse_last3_mean_strength": ("history_payload", "finish_position"),
    "horse_last1_strength": ("history_payload", "finish_position"),
    "horse_days_since": ("races", "race_date"),
    "horse_surface_winrate": ("history", "surface"),
    "horse_surface_starts": ("history", "surface"),
    "horse_track_winrate": ("history", "track"),
    "horse_track_starts": ("history", "track"),
    "horse_dist_winrate": ("history", "distance_m"),
    "horse_dist_starts": ("history", "distance_m"),
    "jockey_log_starts": ("history", "jockey_id"),
    "jockey_prior_winrate": ("history_payload", "finish_position"),
    "jockey_top3rate": ("history_payload", "finish_position"),
    "jockey_track_winrate": ("history", "track"),
    "jockey_surface_winrate": ("history", "surface"),
    "jockey_distance_winrate": ("history", "distance_m"),
    "jockey_last3_mean_strength": ("history_payload", "finish_position"),
    "field_mean_horse_starts": ("field_aggregate", "horse_id"),
    "horse_strength_vs_field": ("field_aggregate", "finish_position"),
    "jockey_strength_vs_field": ("field_aggregate", "finish_position"),
    "field_fraction_new_horses": ("field_aggregate", "horse_id"),
}


def audit(db_path, model_path, limit=1000):
    model = json.loads(Path(model_path).read_text(encoding="utf-8"))
    names = model["feature_names"]
    if len(names) != 31 or len(set(names)) != 31:
        raise ValueError("EXPECTED_31_UNIQUE_MODEL_FEATURES")
    if set(names) != set(FEATURE_SOURCE_FIELDS):
        raise ValueError("FEATURE_COVERAGE_SPEC_DOES_NOT_MATCH_FROZEN_MODEL")
    with sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        cols = {table: {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}
                for table in ("annual_report_races", "annual_report_runners")}
        required = {"annual_report_races": {"race_id", "race_date", "surface", "track", "distance_m", "expected_runners"},
                    "annual_report_runners": {"race_id", "horse_id", "jockey_id", "horse_number", "payload_json"}}
        missing = {k: sorted(v - cols[k]) for k, v in required.items() if v - cols[k]}
        if missing:
            return {"status": "BLOCKED_SCHEMA", "missing_columns": missing}
        counts = collections.Counter()
        for r in db.execute("""
            SELECT h.horse_id, h.jockey_id, h.payload_json, r.race_date
            FROM annual_report_runners h
            JOIN annual_report_races r ON r.race_id=h.race_id
            ORDER BY r.race_date DESC LIMIT ?
        """, (limit,)):
            counts["sampled_rows"] += 1
            if r["horse_id"]: counts["horse_id_present"] += 1
            if r["jockey_id"]: counts["jockey_id_present"] += 1
            try: payload = json.loads(r["payload_json"])
            except (ValueError, TypeError): payload = {}
            for field in ("age", "sex", "carried_weight", "gate", "finish_position"):
                if payload.get(field) is not None: counts["payload_" + field] += 1
        return {
            "status": "AUDITED_NOT_PARITY_VALIDATED",
            "sample": dict(counts),
            "model_feature_count": len(names),
            "feature_source_map": {n: {"source": FEATURE_SOURCE_FIELDS[n][0],
                                       "field": FEATURE_SOURCE_FIELDS[n][1]} for n in names},
            "limitations": [
                "Input column presence is not proof of original V51 feature formula parity.",
                "Retrospective result records are not proof of preoff source availability.",
                "All 31 feature calculations must be matched to original training formulas before inference."
            ]
        }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--database", required=True)
    p.add_argument("--model", default="operations/prediction_policy/standard_v51_model.json")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    result = audit(a.database, a.model, a.limit)
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "sample": result.get("sample")}))
