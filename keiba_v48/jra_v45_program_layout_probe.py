"""Read-only geometry probe for JRA venue-wide program PDFs.

Research candidate only: no network, no identity linking, no production freeze.
The official PDF byte source, observation time and a separately observed official
roster must be verified outside this probe. Never treat its candidates as facts.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

PDF_MAGIC = b'%PDF-'
HORSE_NO = re.compile(r'^(?:[1-9]|1[0-8])$')
WEIGHT = re.compile(r'^(?:[4-5][0-9]|6[0-5])(?:\.\d)?$')
TIME = re.compile(r'(?<!\d)([0-2]?\d)\s*時\s*([0-5]?\d)\s*分')
REVERSED_TIME = re.compile(r'分\s*([0-5]?\d)\s*時\s*([0-2]?\d)')
RACE = re.compile(r'(?<!\d)(1[0-2]|[1-9])\s*R\b|\bR\s*(1[0-2]|[1-9])(?!\d)', re.I)
BAD_NAME = re.compile(r'[0-9０-９]|(?:牡|牝|騎手|負担|検量|集合|発走|馬齢|JPN|Turf|Dirt)')


def _normal(s):
    return re.sub(r'\s+', '', s).replace('　', '')


def _header_time(text):
    # The PDF's embedded glyph order can be reversed: do not silently accept it.
    match = TIME.search(text)
    if match:
        h, m = map(int, match.groups())
        if 8 <= h <= 18 and 0 <= m <= 59:
            return f'{h:02d}:{m:02d}', 'direct'
    match = REVERSED_TIME.search(text)
    if match:
        minute, hour = map(int, match.groups())
        if 8 <= hour <= 18 and 0 <= minute <= 59:
            return f'{hour:02d}:{minute:02d}', 'reversed_glyph_order_unverified'
    return None, 'missing'


def _column(page, page_index, column_index):
    import fitz
    rect = page.rect
    width = rect.width / 4
    left = rect.x0 + width * column_index
    right = left + width
    words = page.get_text('words', clip=fitz.Rect(left, rect.y0, right, rect.y1), sort=True)
    # All positions are normalized to the current venue column.
    tokens = [{'x': (w[0] + w[2]) / 2 - left, 'y': (w[1] + w[3]) / 2 - rect.y0,
               'text': str(w[4])} for w in words]
    head = [w for w in tokens if w['y'] < rect.height * .19]
    header = ' '.join(w['text'] for w in head)
    found = [int(m.group(1) or m.group(2)) for m in RACE.finditer(header)]
    expected_no = page_index * 4 + column_index + 1
    issues = []
    if expected_no not in found:
        issues.append('race_number_not_independently_confirmed')
    if any(n != expected_no for n in found):
        issues.append('header_contains_conflicting_race_number')
    post, time_method = _header_time(header)
    if time_method != 'direct':
        issues.append('post_time_requires_independent_confirmation')
    # Number anchors are only candidates. The source may contain other digits
    # in this band, so we never assert runner extraction as verified.
    anchors = sorted((w for w in tokens if rect.height * .13 <= w['y'] <= rect.height * .96
                      and width * .035 <= w['x'] <= width * .13 and HORSE_NO.fullmatch(w['text'])),
                     key=lambda w: w['y'])
    runners = []
    seen = set()
    for anchor in anchors:
        number = int(anchor['text'])
        if number in seen:
            issues.append('duplicate_horse_number_candidate')
            continue
        seen.add(number)
        y = anchor['y']
        same_row = [w for w in tokens if abs(w['y'] - y) <= max(4, rect.height * .012)]
        names = [w['text'] for w in same_row if width * .15 <= w['x'] <= width * .65
                 and len(_normal(w['text'])) >= 2 and not BAD_NAME.search(w['text'])]
        weights = [w['text'] for w in same_row if width * .66 <= w['x'] <= width * .87
                   and WEIGHT.fullmatch(w['text'])]
        runners.append({'horse_number_candidate': number,
                        'horse_name_candidate': names[0] if len(names) == 1 else None,
                        'weight_candidate': float(weights[0]) if len(weights) == 1 else None,
                        'candidate_name_count': len(names), 'candidate_weight_count': len(weights),
                        'source_y_fraction': round(y / rect.height, 5)})
    if not runners:
        issues.append('no_runner_number_candidates')
    if any(x['horse_name_candidate'] is None or x['weight_candidate'] is None for x in runners):
        issues.append('runner_name_or_weight_ambiguous')
    if runners and sorted(x['horse_number_candidate'] for x in runners) != list(range(1, len(runners) + 1)):
        issues.append('runner_numbers_not_consecutive')
    return {'race_number_expected': expected_no, 'race_number_header_candidates': found,
            'post_time_candidate': post, 'post_time_method': time_method,
            'runner_candidates': runners, 'issues': sorted(set(issues)),
            'verified_for_production': False}


def probe_pdf_bytes(data: bytes, source_url: str | None = None,
                    observed_at: str | None = None) -> dict:
    if not data.startswith(PDF_MAGIC):
        raise ValueError('not_a_pdf')
    import fitz
    try:
        doc = fitz.open(stream=data, filetype='pdf')
    except Exception as exc:
        raise ValueError('invalid_pdf') from exc
    try:
        if doc.is_encrypted or len(doc) != 3:
            raise ValueError('unsupported_page_count_or_encrypted')
        if any(p.rect.width <= p.rect.height for p in doc):
            raise ValueError('expected_landscape_venue_program')
        races = [_column(p, i, col) for i, p in enumerate(doc) for col in range(4)]
    finally:
        doc.close()
    return {'schema': 'jra-program-geometry-probe-v45', 'status': 'CANDIDATES_ONLY_UNVERIFIED',
            'source_url_claimed': source_url, 'observed_at_claimed': observed_at,
            'pdf_sha256': hashlib.sha256(data).hexdigest(), 'pdf_bytes': len(data),
            'race_count': len(races), 'races': races,
            'production_freeze_allowed': False, 'result_settlement_allowed': False,
            'reason': 'Real JRA PDF validation, independent official roster and cancellation reconciliation missing.'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pdf', type=Path, required=True)
    p.add_argument('--source-url', required=True)
    p.add_argument('--observed-at', required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(argv)
    try:
        dt.datetime.fromisoformat(a.observed_at)
    except ValueError as exc:
        raise SystemExit('invalid observed-at ISO8601') from exc
    result = probe_pdf_bytes(a.pdf.read_bytes(), a.source_url, a.observed_at)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'race_count': result['race_count'],
                      'sha256': result['pdf_sha256'], 'production_freeze_allowed': False}))


if __name__ == '__main__':
    main()
