"""Research-only cross-document check: JRA G1 HTML racecard vs venue PDF.

Only compares two observed official page layouts for 2026-10-25 Kyoto 11R.
Does not prove publication before post time, scratches, official horse IDs,
full-venue coverage, or eligibility for production freeze/settlement.
"""
from __future__ import annotations

import hashlib
import re
from bs4 import BeautifulSoup
from jra_v47_program_row_probe import probe_pdf_bytes

G1_URL = "https://www.jra.go.jp/keiba/g1/kikka/syutsuba.html"
PROGRAM_URL = "https://www.jra.go.jp/keiba/rpdf/pdf/20261025-04kyoto09.pdf"
NAME = re.compile(r"^[ァ-ヿぁ-ゖ一-龯ー・･]{2,20}$")
WEIGHT = re.compile(r"(?<!\\d)([45-6]\\d(?:\\.\\d)?)\\s*kg")
HORSE = re.compile(r"^[ァ-ヿぁ-ゖ一-龯ー・･]{2,20}(?=\\s*(?:\\d+(?:\\.\\d+)?|取消|除外|$))")


def _compact(text: str) -> str:
    return re.sub(r"[\\s\\u3000]+", "", text).replace("･", "・")


def _extract_row(tr):
    cells = tr.find_all(["td", "th"], recursive=False)
    if len(cells) < 4:
        return None
    for i in range(min(3, len(cells) - 2)):
        number = _compact(cells[i].get_text(" ", strip=True))
        if not number.isdecimal() or not 1 <= int(number) <= 18:
            continue
        # The number cell must be immediately followed by the horse-name cell,
        # not another number (frame number).
        name_cell = cells[i + 1]
        name = None
        for s in name_cell.stripped_strings:
            candidate = _compact(s)
            if NAME.fullmatch(candidate):
                name = candidate
                break
        if name is None:
            raw = name_cell.get_text(" ", strip=True)
            m = HORSE.match(raw)
            if m:
                name = _compact(m.group())
        if not name:
            continue
        # Current assigned weight belongs to the immediately following cell,
        # never to the previous-race history columns.
        weight_cell = cells[i + 2]
        w = WEIGHT.search(weight_cell.get_text(" ", strip=True))
        if not w:
            continue
        return {"number": int(number), "name": name, "weight": float(w.group(1))}
    return None


def parse_g1_html(raw: bytes) -> dict:
    if not raw or len(raw) > 10 * 1024 * 1024:
        raise ValueError("html_missing_or_oversize")
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text(" ", strip=True)
    if "菊花賞" not in text or "2026年10月25日" not in text or "15時40分" not in text:
        raise ValueError("wrong_race_date_or_post_time")
    tables = []
    for table in soup.find_all("table"):
        rows = [x for tr in table.find_all("tr") if (x := _extract_row(tr)) is not None]
        if rows:
            tables.append(rows)
    # One full racecard table, not a union of fragments and past-run tables.
    candidates = [r for r in tables if len(r) == 18 and sorted(x["number"] for x in r) == list(range(1, 19))]
    if len(candidates) != 1:
        raise ValueError("unique_complete_18_runner_table_not_found")
    rows = sorted(candidates[0], key=lambda x: x["number"])
    if len(set(x["name"] for x in rows)) != 18:
        raise ValueError("duplicate_horse_names")
    return {"source_url": G1_URL, "html_sha256": hashlib.sha256(raw).hexdigest(),
            "runner_count": 18, "post_time": "15:40", "runners": rows}


def compare_kyoto11(pdf: bytes, html: bytes, *, pdf_observed_at: str,
                    html_observed_at: str) -> dict:
    if not pdf_observed_at or not html_observed_at:
        raise ValueError("capture_times_required")
    pdf_probe = probe_pdf_bytes(pdf, PROGRAM_URL, pdf_observed_at)
    html_roster = parse_g1_html(html)
    race = pdf_probe["races"][10]
    issues = []
    if race["race_number_header_candidates"] != [11]:
        issues.append("pdf_race_header_unverified")
    if race["post_time_candidate"] != html_roster["post_time"] or race["post_time_method"] != "direct_text_candidate":
        issues.append("post_time_unverified_or_disagrees")
    pdf_rows = race["runner_candidates"]
    by_no = {x["horse_number_candidate"]: x for x in pdf_rows}
    if len(by_no) != len(pdf_rows) or set(by_no) != set(range(1, 19)):
        issues.append("pdf_runner_numbers_not_exactly_1_to_18")
    matched = 0
    differences = []
    for x in html_roster["runners"]:
        p = by_no.get(x["number"])
        if p is None or _compact(p.get("horse_name_candidate") or "") != x["name"] or p.get("weight_candidate") != x["weight"]:
            differences.append(x["number"])
        else:
            matched += 1
    if differences:
        issues.append("runner_name_or_weight_mismatch")
    # PDF's private-use glyph headcount remains unresolved; do not silently
    # substitute the HTML count for an independent PDF decoding.
    if race["declared_head_count_candidate"] is None:
        issues.append("pdf_printed_headcount_not_machine_decoded")
    issues.extend(x for x in race["issues"] if x != "declared_head_count_missing_or_ambiguous")
    return {
        "schema": "jra-kyoto11-crossdocument-research",
        "status": "RESEARCH_ONLY_POSTRACE",
        "race_date": "2026-10-25", "venue": "京都", "race": 11,
        "pdf_url": PROGRAM_URL, "html_url": G1_URL,
        "pdf_sha256": pdf_probe["pdf_sha256"], "html_sha256": html_roster["html_sha256"],
        "pdf_observed_at_utc": pdf_observed_at, "html_observed_at_utc": html_observed_at,
        "pdf_runner_candidates": len(pdf_rows), "html_runner_count": 18,
        "matched_number_name_weight": matched, "mismatched_numbers": differences,
        "pdf_printed_headcount_decoded": race["declared_head_count_candidate"],
        "issues": sorted(set(issues)),
        "full_crossdocument_match": matched == 18 and not differences and
            not any(x for x in issues if x != "pdf_printed_headcount_not_machine_decoded"),
        "independent_source_is_separate_document": True,
        "underlying_source_independence_proven": False,
        "scratches_authenticated": False, "official_horse_ids_confirmed": 0,
        "preoff_capture_proven": False, "production_freeze_allowed": False,
        "result_settlement_allowed": False, "forward_prediction_fixed": False
    }
