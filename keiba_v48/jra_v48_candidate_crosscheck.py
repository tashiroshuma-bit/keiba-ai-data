"""v48: offline, read-only consistency bridge for v47 PDF candidates and v46 roster.

This NEVER authenticates PDF origin, observation time, scratches or official IDs.
It never authorizes production freeze/settlement, even on a clean match.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import re
from pathlib import Path

from jra_v46_roster_crosscheck import crosscheck as v46_crosscheck

NAME = re.compile(r"^[ァ-ヿぁ-ゖ一-龯ー・･]{2,20}$")


def crosscheck_v47(probe: dict, roster: dict) -> dict:
    """Check all 12 races/runner rows without upgrading untrusted source claims."""
    issues: list[str] = []
    def fail(code: str) -> None:
        issues.append(code)

    if not isinstance(probe, dict) or not isinstance(roster, dict):
        raise ValueError("objects_required")
    if probe.get("schema") != "jra-v47-program-row-probe":
        fail("unexpected_v47_schema")
    if probe.get("status") != "CANDIDATES_ONLY_UNVERIFIED":
        fail("unexpected_probe_status")
    for field, expected in (("source_authenticity_proven", False),
                            ("production_freeze_allowed", False),
                            ("result_settlement_allowed", False),
                            ("official_horse_ids_confirmed", 0)):
        if type(probe.get(field)) is not type(expected) or probe.get(field) != expected:
            fail("unexpected_probe_" + field)
    races = probe.get("races")
    if probe.get("race_count") != 12 or not isinstance(races, list) or len(races) != 12:
        fail("twelve_races_required")
        races = races if isinstance(races, list) else []
    normalized = copy.deepcopy(probe)
    normalized["races"] = []
    seen_races = set()
    for r in races:
        if not isinstance(r, dict):
            fail("non_object_race")
            continue
        n = r.get("race_number_expected")
        if type(n) is not int or not 1 <= n <= 12 or n in seen_races:
            fail("race_number_invalid_or_duplicate")
            continue
        seen_races.add(n)
        if r.get("race_number_header_candidates") != [n]:
            fail(f"race_{n}_header_not_unique")
        if r.get("issues") != [] or r.get("verified_for_production") is not False:
            fail(f"race_{n}_probe_issues_or_unsafe_state")
        if r.get("post_time_method") != "direct_text_candidate":
            fail(f"race_{n}_post_time_unverified")
        runners = r.get("runner_candidates")
        count = r.get("declared_head_count_candidate")
        if not isinstance(runners, list) or type(count) is not int or not 1 <= count <= 18 or len(runners) != count:
            fail(f"race_{n}_runner_count_mismatch")
            runners = runners if isinstance(runners, list) else []
        nums = []
        names = []
        for h in runners:
            if not isinstance(h, dict):
                fail(f"race_{n}_runner_not_object")
                continue
            no = h.get("horse_number_candidate")
            name = h.get("horse_name_candidate")
            weight = h.get("weight_candidate")
            if type(no) is not int or not 1 <= no <= 18:
                fail(f"race_{n}_invalid_runner_number")
            else:
                nums.append(no)
            if not isinstance(name, str) or not NAME.fullmatch(name):
                fail(f"race_{n}_invalid_runner_name")
            else:
                names.append(name.replace("･", "・"))
            if type(weight) not in (int, float) or not math.isfinite(weight) or not 45 <= weight <= 65:
                fail(f"race_{n}_invalid_runner_weight")
            if h.get("name_candidate_count") != 1 or h.get("weight_candidate_count") != 1:
                fail(f"race_{n}_ambiguous_row")
        if sorted(nums) != list(range(1, len(runners) + 1)) or len(set(names)) != len(names):
            fail(f"race_{n}_runner_duplicate_or_gap")
        item = copy.deepcopy(r)
        # v46 uses "direct" for its candidate-consistency test. Translating
        # this label is NOT independent validation or publication proof.
        item["post_time_method"] = "direct" if r.get("post_time_method") == "direct_text_candidate" else "unverified"
        normalized["races"].append(item)
    if seen_races != set(range(1, 13)):
        fail("missing_race_numbers")
    # A separate official roster must not simply cite the PDF as its own source.
    if probe.get("pdf_sha256") == roster.get("independent_roster_sha256"):
        fail("independent_roster_sha_equals_pdf_sha")
    try:
        result = v46_crosscheck(normalized, roster)
        issues.extend("v46:" + x for x in result["issues"])
        matched = result["matched_runner_rows"]
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError) as exc:
        fail("v46_input_rejected:" + type(exc).__name__)
        matched = 0
    issues = sorted(set(issues))
    return {
        "schema": "jra-v48-candidate-crosscheck", "status": "RESEARCH_ONLY",
        "candidate_consistency_pass": not issues, "matched_runner_rows": matched,
        "issues": issues, "source_authenticity_proven": False,
        "official_horse_ids_confirmed": 0, "production_freeze_allowed": False,
        "result_settlement_allowed": False, "forward_prediction_fixed": False,
        "reason": "Both JSONs and observed-at values are claims. v47/v46 consistency cannot prove original bytes, independent source authenticity, scratch updates or pre-off capture."
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--v47-probe", type=Path, required=True)
    ap.add_argument("--independent-roster", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    result = crosscheck_v47(json.loads(a.v47_probe.read_text(encoding="utf-8")),
                            json.loads(a.independent_roster.read_text(encoding="utf-8")))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"candidate_consistency_pass": result["candidate_consistency_pass"],
                      "issue_count": len(result["issues"]), "production_freeze_allowed": False}))


if __name__ == "__main__":
    main()
