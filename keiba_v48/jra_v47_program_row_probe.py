"""Offline, research-only JRA venue-program PDF row-layout probe (v47).

This does NOT authenticate provenance, publication time, official horse IDs,
runner scratches, or official results. It cannot authorize production freeze.
The actual JRA PDF has NOT been byte-validated with this version.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

PDF_MAGIC = b"%PDF-"
NO = re.compile(r"^(?:[1-9]|1[0-8])$")
WEIGHT = re.compile(r"^(?:4[5-9]|5[0-9]|6[0-5])(?:\.\d)?$")
HORSE_NAME = re.compile(r"^[ァ-ヿぁ-ゖ一-龯ー・･]{2,20}$")
HORSE_PART = re.compile(r"^[ァ-ヿぁ-ゖ一-龯ー・･]{1,20}$")
TIME_DIRECT = re.compile(r"(?<!\d)([89]|1[0-8])\s*時\s*([0-5]?\d)\s*分")
TIME_REVERSED = re.compile(r"分\s*([0-5]?\d)\s*時\s*([89]|1[0-8])")
RACE = re.compile(r"(?<!\d)(1[0-2]|[1-9])\s*R\b|\bR\s*(1[0-2]|[1-9])(?!\d)", re.I)
HEAD_COUNT = re.compile(r"(?<!\d)(\d{1,2})\s*頭|頭\s*(\d{1,2})(?!\d)")


def _clean(value: str) -> str:
    return re.sub(r"[\s\u3000]+", "", value).replace("･", "・")


def _spans(page, x0: float, x1: float):
    """Return original span bounding boxes; do not trust text extraction order."""
    import fitz
    raw = page.get_text("dict", clip=fitz.Rect(x0, page.rect.y0, x1, page.rect.y1))
    out = []
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for s in line.get("spans", []):
                txt = _clean(s.get("text", ""))
                if txt:
                    x_a, y_a, x_b, y_b = s["bbox"]
                    out.append({"text": txt, "x": (x_a + x_b) / 2 - x0,
                                "y": (y_a + y_b) / 2 - page.rect.y0,
                                "size": s.get("size", 0.0)})
    return out


def _name_from_same_baseline(row: list[dict], width: float, height: float) -> tuple[str | None, int]:
    """Research-only reconstruction of PDF glyphs spaced into separate spans.

    Reject baseline disagreement and overlapping spans rather than joining
    arbitrary nearby Japanese text. The independent roster must still verify
    the reconstructed name; this is not a trusted official ID.
    """
    parts = sorted((s for s in row if .15 * width <= s["x"] <= .53 * width
                    and s["size"] >= 7 and HORSE_PART.fullmatch(s["text"])),
                   key=lambda s: s["x"])
    if not parts:
        return None, 0
    if max(s["y"] for s in parts) - min(s["y"] for s in parts) > .006 * height:
        return None, len(parts)
    for prev, cur in zip(parts, parts[1:]):
        # Approximate Japanese glyph advance by its font size. Two complete
        # names printed on top of one another must not be concatenated.
        prev_right = prev["x"] + len(prev["text"]) * prev["size"] * .48
        cur_left = cur["x"] - len(cur["text"]) * cur["size"] * .48
        if prev_right >= cur_left:
            return None, len(parts)
    name = "".join(s["text"] for s in parts).replace("･", "・")
    if not HORSE_NAME.fullmatch(name):
        return None, len(parts)
    return name, len(parts)


def _race_column(page, page_no: int, col: int) -> dict:
    W = page.rect.width / 4
    H = page.rect.height
    left = page.rect.x0 + col * W
    spans = _spans(page, left, left + W)
    expected = page_no * 4 + col + 1
    issues = []
    # 2026-10-25 Tokyo official visual layout: weight near x=50-65%,
    # unlike v45's unvalidated 66-87% weight search band.
    header = " ".join(s["text"] for s in spans if s["y"] < .17 * H)
    race_numbers = [int(m.group(1) or m.group(2)) for m in RACE.finditer(header)]
    if race_numbers != [expected]:
        issues.append("race_header_missing_ambiguous_or_conflicting")
    head_matches = [int(m.group(1) or m.group(2)) for m in HEAD_COUNT.finditer(header)]
    head_count = head_matches[0] if len(head_matches) == 1 and 1 <= head_matches[0] <= 18 else None
    if head_count is None:
        issues.append("declared_head_count_missing_or_ambiguous")
    tm = TIME_DIRECT.search(header)
    if tm:
        post = f"{int(tm.group(1)):02d}:{int(tm.group(2)):02d}"
        time_method = "direct_text_candidate"
    else:
        tm = TIME_REVERSED.search(header)
        post = f"{int(tm.group(2)):02d}:{int(tm.group(1)):02d}" if tm else None
        time_method = "reversed_glyph_order_unverified" if tm else "missing"
        issues.append("post_time_not_directly_readable")
    # 2026-10-30 real JRA byte probe: printed horse-number glyphs have
    # x/W about .097-.183 and font size about 10.8-11.5.  Larger 17-18pt
    # frame numbers were being mistaken for runners, while real runner
    # numbers in the first two columns were skipped entirely.
    anchors = sorted((s for s in spans if .145 * H < s["y"] < .975 * H
                      and .07 * W <= s["x"] <= .21 * W
                      and 9 <= s["size"] <= 14
                      and NO.fullmatch(s["text"])),
                     key=lambda s: s["y"])
    seen = set()
    runners = []
    for a in anchors:
        n = int(a["text"])
        if n in seen:
            issues.append("duplicate_runner_anchor")
            continue
        seen.add(n)
        # Inspect only the primary printed row; pedigree text is below it.
        # Segmented/ambiguous Japanese glyphs remain unresolved, never guessed.
        # The horse number baseline is offset by ~.014 page heights from
        # name/weight in several real columns. Adjacent horse rows are
        # separated by >=.05 heights in the observed sample.
        row = [s for s in spans if abs(s["y"] - a["y"]) <= .021 * H]
        name, name_parts = _name_from_same_baseline(row, W, H)
        weights = [s["text"] for s in row if .49 * W <= s["x"] <= .66 * W
                   and WEIGHT.fullmatch(s["text"])]
        runners.append({"horse_number_candidate": n,
                        "horse_name_candidate": name,
                        "weight_candidate": float(weights[0]) if len(weights) == 1 else None,
                        "name_candidate_count": 1 if name is not None else name_parts,
                        "name_part_count": name_parts,
                        "weight_candidate_count": len(weights),
                        "anchor_y_fraction": round(a["y"] / H, 5)})
    if not runners:
        issues.append("no_runner_anchors")
    if head_count is not None and len(runners) != head_count:
        issues.append("runner_count_disagrees_with_header")
    if len(runners) > 18 or sorted(r["horse_number_candidate"] for r in runners) != list(range(1, len(runners) + 1)):
        issues.append("runner_numbers_not_consecutive_or_exceed_limit")
    if any(r["horse_name_candidate"] is None or r["weight_candidate"] is None for r in runners):
        issues.append("name_or_weight_ambiguous")
    return {"race_number_expected": expected, "race_number_header_candidates": race_numbers,
            "declared_head_count_candidate": head_count,
            "post_time_candidate": post, "post_time_method": time_method,
            "runner_candidates": runners, "issues": sorted(set(issues)),
            "verified_for_production": False}


def probe_pdf_bytes(data: bytes, source_url_claimed: str | None = None,
                    observed_at_claimed: str | None = None) -> dict:
    if not data.startswith(PDF_MAGIC):
        raise ValueError("not_a_pdf")
    import fitz
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ValueError("invalid_pdf") from exc
    try:
        if doc.is_encrypted or len(doc) != 3 or any(p.rect.width <= p.rect.height for p in doc):
            raise ValueError("unsupported_pdf_geometry_or_encrypted")
        races = [_race_column(p, i, c) for i, p in enumerate(doc) for c in range(4)]
    finally:
        doc.close()
    return {"schema": "jra-v47-program-row-probe", "status": "CANDIDATES_ONLY_UNVERIFIED",
            "source_url_claimed": source_url_claimed,
            "observed_at_claimed": observed_at_claimed,
            "pdf_sha256": hashlib.sha256(data).hexdigest(), "pdf_bytes": len(data),
            "race_count": len(races), "races": races,
            "source_authenticity_proven": False, "official_horse_ids_confirmed": 0,
            "production_freeze_allowed": False, "result_settlement_allowed": False,
            "reason": "Synthetic geometry only. Real PDF bytes, independent official roster, scratch notices and observed publication times are unverified."}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--source-url-claimed", required=True)
    ap.add_argument("--observed-at-claimed", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    result = probe_pdf_bytes(args.pdf.read_bytes(), args.source_url_claimed, args.observed_at_claimed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "race_count": result["race_count"],
                      "pdf_sha256": result["pdf_sha256"], "production_freeze_allowed": False}))


if __name__ == "__main__":
    main()
