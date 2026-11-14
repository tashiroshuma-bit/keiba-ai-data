"""Forecast-first V51 pipeline: reproducible, fail-closed, independently verified.

This orchestrator does not invent JRA data. It consumes an authenticated,
point-in-time snapshot and canonical database, then runs the frozen V51 model.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DB_SHA = "5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd"


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
        tmp = Path(f.name)
    os.replace(tmp, path)


def run(snapshot, database, output_dir):
    snapshot, database, output_dir = Path(snapshot), Path(database), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "jra-v51-forecast-first-run-v1",
        "version": "v51",
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "snapshot": str(snapshot),
        "database": str(database),
        "steps": [],
        "status": "FAILED",
    }

    def step(name, command):
        p = subprocess.run([sys.executable, *command], cwd=ROOT, capture_output=True, text=True)
        manifest["steps"].append({
            "step": name, "returncode": p.returncode,
            "stdout": p.stdout[-12000:], "stderr": p.stderr[-12000:]
        })
        atomic_json(output_dir / "run_manifest.json", manifest)
        if p.returncode:
            raise RuntimeError(f"{name}: exit {p.returncode}")

    try:
        if not snapshot.is_file():
            raise FileNotFoundError("VERIFIED_PREOFF_SNAPSHOT_MISSING")
        if not database.is_file():
            raise FileNotFoundError("CANONICAL_DATABASE_MISSING")
        manifest["snapshot_sha256"] = digest(snapshot)
        manifest["database_sha256"] = digest(database)
        if manifest["database_sha256"] != DB_SHA:
            raise ValueError("CANONICAL_DATABASE_SHA_MISMATCH")
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as conn:
            integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"CANONICAL_SQLITE_QUICK_CHECK_FAILED: {integrity}")
        step("preflight", ["scripts/v51_preoff_diagnostics.py",
            "--snapshot", str(snapshot), "--database", str(database),
            "--model", "operations/prediction_policy/standard_v51_model.json",
            "--policy", "operations/prediction_policy/standard_v51.json"])
        forecast = output_dir / "forecast.json"
        if forecast.exists():
            raise FileExistsError("IMMUTABLE_FORECAST_ALREADY_EXISTS")
        step("inference", ["scripts/standard_v51_forecast.py",
            "--features", str(snapshot), "--database", str(database),
            "--output", str(forecast)])
        step("independent_verification", ["scripts/v51_verify_forecast_json.py",
            "--forecast", str(forecast)])
        # Verify serialized bytes, not merely in-memory predictions.
        loaded = json.loads(forecast.read_text(encoding="utf-8"))
        if loaded["input_sha256"] != manifest["snapshot_sha256"]:
            raise ValueError("FORECAST_INPUT_PROVENANCE_MISMATCH")
        manifest["forecast_sha256"] = digest(forecast)
        manifest["race_count"] = len(loaded["races"])
        manifest["status"] = "VERIFIED"
    except Exception as e:
        manifest["error"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        manifest["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        atomic_json(output_dir / "run_manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot", required=True)
    p.add_argument("--database", required=True)
    p.add_argument("--output-dir", required=True)
    a = p.parse_args()
    print(json.dumps(run(a.snapshot, a.database, a.output_dir), ensure_ascii=False))
