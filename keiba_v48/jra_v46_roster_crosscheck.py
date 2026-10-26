"""Research-only independent JRA roster cross-check of v45 PDF candidates.

Inputs are *claims* unless separately acquired and hashed. Never unlock production
freeze, official horse-ID linkage, or settlement based on this output.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import re
from pathlib import Path
from urllib.parse import urlparse

PDF_URL = re.compile(r'^/keiba/rpdf/pdf/(\d{8})-[\w-]+\.pdf$')
SHA = re.compile(r'^[0-9a-f]{64}$')

def _when(value):
    try:
        x = dt.datetime.fromisoformat(value)
        if x.utcoffset() is None:
            raise ValueError('timezone_required')
        return x
    except (ValueError, TypeError) as e:
        raise ValueError('invalid_offset_datetime') from e

def _official_url(url):
    p = urlparse(url or '')
    return p.scheme == 'https' and p.hostname == 'www.jra.go.jp' and not p.username and not p.password and p.port in (None, 443) and not p.query and not p.fragment

def _name(s):
    return re.sub(r'[\s\u3000]+', '', str(s or '')).replace('･', '・')

def crosscheck(probe: dict, roster: dict) -> dict:
    issues = []
    def bad(tag):
        issues.append(tag)
    url = probe.get('source_url_claimed')
    if not _official_url(url) or not PDF_URL.fullmatch(urlparse(url or '').path):
        bad('pdf_url_not_official_pattern')
    if probe.get('status') != 'CANDIDATES_ONLY_UNVERIFIED' or probe.get('production_freeze_allowed') is not False:
        bad('unexpected_probe_state')
    if not SHA.fullmatch(str(probe.get('pdf_sha256', ''))):
        bad('pdf_sha_missing')
    if roster.get('pdf_sha256') != probe.get('pdf_sha256'):
        bad('pdf_sha_disagrees')
    if roster.get('pdf_url') != url:
        bad('pdf_url_disagrees')
    other_url = roster.get('independent_roster_url')
    if not _official_url(other_url) or other_url == url:
        bad('independent_roster_url_invalid_or_same')
    if not SHA.fullmatch(str(roster.get('independent_roster_sha256', ''))):
        bad('independent_roster_sha_missing')
    try:
        t_pdf = _when(probe.get('observed_at_claimed'))
        t_roster = _when(roster.get('independent_roster_observed_at'))
        if t_roster < t_pdf - dt.timedelta(days=14):
            bad('roster_observation_stale')
    except ValueError:
        bad('observation_timestamp_missing_or_naive')
        t_pdf = t_roster = None
    date_match = PDF_URL.fullmatch(urlparse(url or '').path)
    if date_match and roster.get('race_date') != date_match.group(1):
        bad('race_date_disagrees')
    candidates = probe.get('races', [])
    refs = roster.get('races', [])
    if not isinstance(candidates, list) or not isinstance(refs, list) or len(candidates) != 12 or len(refs) != 12:
        bad('twelve_races_required')
        candidates = candidates if isinstance(candidates, list) else []
        refs = refs if isinstance(refs, list) else []
    cidx = {r.get('race_number_expected'): r for r in candidates if isinstance(r, dict)}
    ridx = {r.get('race_number'): r for r in refs if isinstance(r, dict)}
    if sorted(x for x in cidx if isinstance(x, int)) != list(range(1, 13)) or len(cidx) != len(candidates):
        bad('candidate_race_numbers_invalid_or_duplicate')
    if sorted(x for x in ridx if isinstance(x, int)) != list(range(1, 13)) or len(ridx) != len(refs):
        bad('roster_race_numbers_invalid_or_duplicate')
    matched = 0
    for n in range(1, 13):
        a, b = cidx.get(n), ridx.get(n)
        if not a or not b:
            bad(f'race_{n}_missing')
            continue
        if a.get('issues') or a.get('post_time_method') != 'direct':
            bad(f'race_{n}_probe_ambiguous')
        if a.get('race_number_header_candidates') != [n]:
            bad(f'race_{n}_header_not_unique')
        if a.get('post_time_candidate') != b.get('post_time'):
            bad(f'race_{n}_post_time_mismatch')
        try:
            if t_pdf and t_roster:
                post = dt.datetime.fromisoformat(roster['race_date'] + 'T' + b['post_time'] + ':00+09:00')
                if t_pdf >= post or t_roster >= post:
                    bad(f'race_{n}_not_preoff_observed')
        except (ValueError, KeyError, TypeError):
            bad(f'race_{n}_post_time_invalid')
        ar = a.get('runner_candidates', [])
        br = b.get('runners', [])
        if not isinstance(ar, list) or not isinstance(br, list) or not br:
            bad(f'race_{n}_runners_missing')
            continue
        aa = {h.get('horse_number_candidate'): h for h in ar if isinstance(h, dict)}
        bb = {h.get('number'): h for h in br if isinstance(h, dict)}
        if len(aa) != len(ar) or len(bb) != len(br):
            bad(f'race_{n}_duplicate_runner_number')
        if set(aa) != set(bb):
            bad(f'race_{n}_runner_numbers_disagree')
        if any(h.get('status') != 'running' for h in br):
            bad(f'race_{n}_scratches_need_separate_proof')
        for number, h in aa.items():
            ref = bb.get(number)
            if not ref or not _name(h.get('horse_name_candidate')) or _name(h.get('horse_name_candidate')) != _name(ref.get('name')):
                bad(f'race_{n}_horse_{number}_name_disagrees')
                continue
            try:
                if abs(float(h['weight_candidate']) - float(ref['weight'])) > 0.001:
                    bad(f'race_{n}_horse_{number}_weight_disagrees')
                    continue
            except (TypeError, ValueError, KeyError):
                bad(f'race_{n}_horse_{number}_weight_missing')
                continue
            matched += 1
    issues = sorted(set(issues))
    return {'schema': 'jra-v46-independent-roster-crosscheck', 'candidate_consistency_pass': not issues,
            'matched_runner_rows': matched, 'issues': issues,
            'source_authenticity_proven': False, 'official_horse_ids_confirmed': 0,
            'production_freeze_allowed': False, 'result_settlement_allowed': False,
            'reason': 'JSON inputs are untrusted claims; independent original bytes, provenance, scratches and pre-off evidence must be authenticated outside this research cross-check.'}

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--probe', type=Path, required=True)
    p.add_argument('--roster', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(argv)
    result = crosscheck(json.loads(a.probe.read_text(encoding='utf-8')),
                        json.loads(a.roster.read_text(encoding='utf-8')))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'candidate_consistency_pass': result['candidate_consistency_pass'],
                      'issue_count': len(result['issues']), 'production_freeze_allowed': False}))

if __name__ == '__main__':
    main()
