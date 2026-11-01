"""Fail-closed v50 production promotion audit. No model mutation or synthetic evidence."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def evaluate(state, evidence):
    failures = []
    def require(condition, why):
        if not condition:
            failures.append(why)
    require(state.get("database", {}).get("version", 0) >= 10, "canonical database version")
    require(state.get("active_model", {}).get("live_bet_generation") is False,
            "live betting must remain disabled during evaluation")
    require(evidence.get("candidate_version") == "v50", "candidate identity")
    require(evidence.get("canonical_db_sha256") == state.get("database", {}).get("sha256"), "DB hash")
    require(bool(evidence.get("candidate_model_sha256")), "candidate weights hash")
    require(bool(evidence.get("independent_calibration", {}).get("verified")), "independent calibration")
    require(bool(evidence.get("independent_calibration", {}).get("source_hash")), "calibration source hash")
    races = evidence.get("races", [])
    require(isinstance(races, list) and len(races) >= 100, "100 forward races required")
    seen = set()
    for i, race in enumerate(races if isinstance(races, list) else []):
        rid = race.get("race_id") if isinstance(race, dict) else None
        require(bool(rid) and rid not in seen, f"race {i}: unique race ID")
        if rid: seen.add(rid)
        if not isinstance(race, dict): continue
        require(bool(race.get("prediction_sha256")) and bool(race.get("input_sha256")),
                f"race {i}: frozen prediction and input hashes")
        require(bool(race.get("result_sha256")), f"race {i}: official result hash")
        require(race.get("frozen_before_off") is True, f"race {i}: actual pre-off freeze")
        require(race.get("roster_independently_verified") is True, f"race {i}: roster verification")
        require(race.get("result_independently_verified") is True, f"race {i}: result verification")
        require(race.get("no_postoff_features") is True, f"race {i}: no post-off leakage")
    metrics = evidence.get("independent_metrics", {})
    for key in ("winner_hit", "top3_all_hit", "ordered_all_hit", "mean_rank_log_loss", "brier"):
        value = metrics.get(key)
        require(isinstance(value, (int, float)) and not isinstance(value, bool), "metric: " + key)
    require(evidence.get("replay_verified") is True, "deterministic replay")
    require(evidence.get("all_ci_passed") is True, "full CI suite")
    return {"approved": not failures, "failures": failures, "forward_races": len(races) if isinstance(races,list) else 0}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--state", type=Path, default=ROOT / "PROJECT_STATE.json")
    args = parser.parse_args()
    state = json.loads(args.state.read_text(encoding="utf-8"))
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    outcome = evaluate(state, evidence)
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    raise SystemExit(0 if outcome["approved"] else 1)

if __name__ == "__main__":
    main()
