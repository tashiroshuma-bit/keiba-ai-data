"""Read-only audit of append-only forward prediction evidence; never creates forecasts."""
import argparse
import datetime as dt
import hashlib
import json
import sqlite3
from pathlib import Path


def _time(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("naive timestamp")
    return parsed.astimezone(dt.timezone.utc)


def audit(path):
    conn = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)
    try:
        records = conn.execute(
            "SELECT id,race_id,model_hash,mode,created_at,payload FROM predictions ORDER BY created_at,id"
        ).fetchall()
        issues, eligible, seen = [], [], set()
        for key, race_id, model_hash, mode, stored_at, raw in records:
            if mode != "forward":
                continue
            try:
                p = json.loads(raw)
                model = p["model_artifact"]
                expected_model = hashlib.sha256(
                    json.dumps(model, sort_keys=True, ensure_ascii=False, allow_nan=False,
                               separators=(",", ":")).encode()).hexdigest()
                expected_key = hashlib.sha256((mode + expected_model + raw).encode()).hexdigest()
                if key != expected_key or model_hash != expected_model:
                    raise ValueError("fingerprint mismatch")
                if p["race_id"] != race_id or p.get("deployment_status") not in (
                        "experimental_rank_shadow", "experimental_probability"):
                    raise ValueError("race or deployment mismatch")
                created, cutoff, off = map(_time, (stored_at, p["cutoff_timestamp"], p["off_timestamp"]))
                if not created < cutoff <= off:
                    raise ValueError("not frozen before cutoff/off")
                if _time(p["created_at"]) > cutoff:
                    raise ValueError("payload created after cutoff")
                runners = p["runners"]
                if not runners or len({str(r["horse_number"]) for r in runners}) != len(runners):
                    raise ValueError("incomplete/duplicate runner numbers")
                inputs = p.get("inputs", {}).get("runners", [])
                if len(inputs) != len(runners):
                    raise ValueError("input runner count mismatch")
                if any(_time(r["features_asof"]) > created for r in inputs):
                    raise ValueError("unobserved runner input")
                if p.get("allocation", {}).get("bets"):
                    raise ValueError("unapproved bet generation")
                if race_id in seen:
                    raise ValueError("multiple forward freezes for same race")
                seen.add(race_id)
                eligible.append(key)
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                issues.append({"prediction_id": key, "race_id": race_id, "reason": str(exc)})
        return {"forward_rows": sum(r[3] == "forward" for r in records),
                "eligible_forward_races": len(eligible), "eligible_ids": eligible,
                "rejected": issues, "status": "pass" if not issues else "fail"}
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = audit(args.ledger)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(output + "\n")
    print(output)
    raise SystemExit(bool(result["rejected"]))
