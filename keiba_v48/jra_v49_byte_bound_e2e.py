"""v49 offline JRA venue PDF + independent roster *byte-bound* research check.

Never authenticates origin, capture time, official IDs, scratches, or results.
Never unlocks production freeze/settlement. Raw source bytes stay local.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from jra_v47_program_row_probe import probe_pdf_bytes
from jra_v48_candidate_crosscheck import crosscheck_v47

MAX_BYTES = 20 * 1024 * 1024


def _read_limited(path: Path, *, pdf: bool) -> bytes:
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError("source_missing_empty_or_oversize")
    data = path.read_bytes()
    if pdf and not data.startswith(b"%PDF-"):
        raise ValueError("program_not_pdf")
    return data


def inspect_bytes(program: bytes, independent_raw: bytes, roster: dict,
                  program_url: str, observed_at_claimed: str) -> dict:
    """Bind source bytes to claimed hashes before calling research-only v47/v48.

    A passing candidate comparison is not source authentication. In particular,
    roster JSON may have been transcribed or derived from the program itself.
    """
    issues = []
    if not isinstance(roster, dict):
        raise ValueError("roster_object_required")
    if not program.startswith(b"%PDF-"):
        raise ValueError("program_not_pdf")
    if not independent_raw:
        raise ValueError("independent_source_empty")
    if len(program) > MAX_BYTES or len(independent_raw) > MAX_BYTES:
        raise ValueError("source_oversize")
    program_sha = hashlib.sha256(program).hexdigest()
    independent_sha = hashlib.sha256(independent_raw).hexdigest()
    if program_sha == independent_sha:
        issues.append("independent_bytes_identical_to_program")
    if roster.get("pdf_sha256") != program_sha:
        issues.append("roster_program_sha_not_bound_to_bytes")
    if roster.get("independent_roster_sha256") != independent_sha:
        issues.append("roster_independent_sha_not_bound_to_bytes")
    if roster.get("pdf_url") != program_url:
        issues.append("roster_program_url_disagrees")
    # This metadata is a user-supplied claim, NOT an authenticated fetch log.
    try:
        probe = probe_pdf_bytes(program, program_url, observed_at_claimed)
        check = crosscheck_v47(probe, roster)
    except (ValueError, TypeError, KeyError, ImportError, RuntimeError) as exc:
        issues.append("probe_or_crosscheck_failed:" + type(exc).__name__)
        check = {"candidate_consistency_pass": False, "matched_runner_rows": 0,
                 "issues": ["probe_not_completed"]}
    issues.extend(check.get("issues", []))
    issues = sorted(set(issues))
    return {"schema": "jra-v49-byte-bound-research-e2e",
            "status": "RESEARCH_ONLY_UNAUTHENTICATED",
            "program_pdf_sha256_computed": program_sha,
            "independent_raw_sha256_computed": independent_sha,
            "program_pdf_bytes": len(program),
            "independent_raw_bytes": len(independent_raw),
            "candidate_consistency_pass": not issues and check.get("candidate_consistency_pass") is True,
            "matched_runner_rows": check.get("matched_runner_rows", 0),
            "issues": issues,
            "byte_hashes_bound": not any(x.startswith("roster_") or x == "independent_bytes_identical_to_program" for x in issues),
            "source_authenticity_proven": False,
            "capture_time_authenticated": False,
            "independent_roster_transcription_authenticated": False,
            "scratches_authenticated": False,
            "official_horse_ids_confirmed": 0,
            "production_freeze_allowed": False,
            "result_settlement_allowed": False,
            "forward_prediction_fixed": False,
            "reason": "Local source bytes are hashed and bound to JSON claims; actual HTTP provenance, capture timestamps, independent transcription, scratches and official IDs remain unverified."}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--program-pdf", type=Path, required=True)
    ap.add_argument("--independent-roster-raw", type=Path, required=True)
    ap.add_argument("--roster-json", type=Path, required=True)
    ap.add_argument("--program-url-claimed", required=True)
    ap.add_argument("--observed-at-claimed", required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    paths = [a.program_pdf.resolve(), a.independent_roster_raw.resolve(), a.roster_json.resolve(), a.out.resolve()]
    if len(set(paths)) != len(paths):
        ap.error("all_input_and_output_paths_must_be_distinct")
    try:
        p = _read_limited(a.program_pdf, pdf=True)
        r = _read_limited(a.independent_roster_raw, pdf=False)
        roster_bytes = _read_limited(a.roster_json, pdf=False)
        roster = json.loads(roster_bytes.decode("utf-8"))
        result = inspect_bytes(p, r, roster, a.program_url_claimed, a.observed_at_claimed)
    except (ValueError, UnicodeError, OSError, json.JSONDecodeError) as exc:
        ap.error(str(exc))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"],
                      "candidate_consistency_pass": result["candidate_consistency_pass"],
                      "issue_count": len(result["issues"]),
                      "production_freeze_allowed": False}))


if __name__ == "__main__":
    main()
