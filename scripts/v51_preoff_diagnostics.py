"""Read-only v51 preflight. Never fabricates runner features or overrides fail-closed inference."""
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def ts(value):
    result = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timezone required")
    return result


def check(snapshot, database, model, policy):
    p = json.loads(Path(policy).read_text(encoding="utf-8"))
    expected = p["expected_canonical_db_sha256"]
    issues = []
    if not Path(database).is_file():
        issues.append("database:MISSING")
    elif sha(database) != expected:
        issues.append("database:SHA_MISMATCH")
    if not Path(model).is_file():
        issues.append("model:MISSING")
    else:
        m = json.loads(Path(model).read_text(encoding="utf-8"))
        if m.get("production_enabled") is not True or m.get("feature_count") != 31:
            issues.append("model:UNAPPROVED_OR_NOT_31_FEATURES")
    if not Path(snapshot).is_file():
        issues.append("snapshot:MISSING")
        return {"status": "NOT_READY", "issues": issues}
    d = json.loads(Path(snapshot).read_text(encoding="utf-8"))
    if d.get("schema") != p["requires_feature_schema"] or d.get("canonical_database_sha256") != expected:
        issues.append("snapshot:SCHEMA_OR_CANONICAL_SHA_MISMATCH")
    try:
        asof = ts(d["forecast_asof"])
    except (KeyError, TypeError, ValueError):
        issues.append("snapshot:INVALID_ASOF")
        asof = None
    if not d.get("roster_source_url") or not d.get("roster_source_sha256"):
        issues.append("snapshot:MISSING_ROSTER_PROOF")
    races = d.get("races", [])
    if not races:
        issues.append("snapshot:NO_RACES")
    for r in races:
        rid = str(r.get("race", "UNKNOWN"))
        try:
            if asof is not None and ts(r["race_off_at"]) <= asof:
                issues.append(rid + ":NOT_PREOFF")
        except (KeyError, TypeError, ValueError):
            issues.append(rid + ":INVALID_OFF_TIME")
        horses = r.get("horses", [])
        if len(horses) < 3 or len({str(h.get("number")) for h in horses}) != len(horses):
            issues.append(rid + ":INVALID_ROSTER")
        for h in horses:
            prefix = rid + "/" + str(h.get("number", "?"))
            if not str(h.get("horse_id", "")).startswith("jra:") or not isinstance(h.get("official_identity_proof"), dict):
                issues.append(prefix + ":MISSING_ID_PROOF")
            v = h.get("feature_values")
            if not isinstance(v, list) or len(v) != 31 or any(type(x) not in (float, int) or not math.isfinite(x) for x in v):
                issues.append(prefix + ":INVALID_FEATURES")
            try:
                if asof is not None and ts(h["features_observed_at"]) > asof:
                    issues.append(prefix + ":FEATURE_AFTER_ASOF")
            except (KeyError, TypeError, ValueError):
                issues.append(prefix + ":MISSING_FEATURE_TIMESTAMP")
    return {"status": "NOT_READY" if issues else "PREFLIGHT_PASSED_NOT_OFFICIAL", "race_count": len(races), "issues": issues}


def main():
    a = argparse.ArgumentParser()
    for name in ("snapshot", "database", "model", "policy"):
        a.add_argument("--" + name, required=True)
    args = a.parse_args()
    report = check(args.snapshot, args.database, args.model, args.policy)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(2 if report["issues"] else 0)


if __name__ == "__main__":
    main()
