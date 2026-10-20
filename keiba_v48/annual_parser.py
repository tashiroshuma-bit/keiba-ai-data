"""Position-based annual-report extraction with fail-closed race audits.

Adobe Japan1 CIDs 9872..9881 are the numeric glyph series, verified against
the rendered official report. Unknown custom-font glyphs remain unresolved.
"""
import argparse
import concurrent.futures
import datetime as dt
import json
import re
import unicodedata

import pdfplumber
from pdfplumber.utils import extract_text
from annual_reports import connect, VENUES

VERSION = 'annual-layout-6'


def normalize(value):
    value = re.sub(r'\(cid:(\d+)\)',
                   lambda m: str(int(m[1]) - 9872) if 9872 <= int(m[1]) <= 9881 else m[0], value)
    return unicodedata.normalize('NFKC', value).replace('−', '-').replace('―', '-')


def compact(value):
    return re.sub(r'\s+', '', value)


def cell(chars, left, right, top, tolerance=1.4):
    selected = [c for c in chars if left <= c['x0'] < right and abs(c['top'] - top) <= tolerance]
    return ''.join(c['text'] for c in sorted(selected, key=lambda c: c['x0'])).strip()


def read_panel(chars, job, page_number, panel, outline_recovered=False):
    raw = extract_text(chars, x_tolerance=1, y_tolerance=2) or ''
    text = normalize(raw)
    # Program-change appendices are notices, not another result panel.
    if '競馬番組' in text[:150] and '競走の取りやめ' in compact(text):
        return None
    result_header = re.split(r'本\s*賞|負担重量', text, maxsplit=1)[0]
    # Footnotes can mention a different race number. Never use that as this
    # panel's identity when a jump title prints the actual number separately.
    race_match = re.search(r'第\s*(\d+)\s*競走', result_header)
    if not race_match:
        # In graded jump reports the large race number is printed ABOVE the
        # ordinary header, on the title's line, leaving "第 競走" below.
        race_match = re.search(r'(?:^|\n)\s*(\d{1,2})\s+(?=[^\n]*ジャンプ)', result_header)
    inferred_race_number = False
    if not race_match:
        if not outline_recovered or '競走' not in compact(text) or page_number > 6:
            return None
        number = (page_number - 1) * 2 + panel + 1
        inferred_race_number = True
    else:
        number = int(race_match[1])
    race_id = f"{job['year']}{VENUES[job['venue']][0]}{job['meeting']:02}{job['day']:02}{number:02}"
    issues = []
    if outline_recovered:
        issues.append('outlined numeric glyph recovery requires review')
    if inferred_race_number:
        issues.append('race number inferred from page order; not source-verified')
    date = re.search(r'\d{5}\s*(\d{1,2})月\s*(\d{1,2})日\s+([^\n]+)', text)
    if not date:
        date = re.search(r'(?<!\d)(\d{1,2})月\s*(\d{1,2})日\s+([^\n]+)', text)
    off = re.search(r'発走\s*(\d+)時\s*(\d+)分', text)
    count = re.search(r'\(\s*(\d+)\s*頭\s*\)', text)
    header = text[:text.find('負担重量')] if '負担重量' in text else text[:500]
    distance = re.search(r'(\d[\d,]*)\s*(?:\(cid:\d+\)|メートル|m)\s*\n', header)
    if not distance:
        distance = re.search(r'(\d{1,2},\d{3})', header)
    surface = 'dirt' if 'ダート' in header else ('turf' if '芝' in header else '')
    if '障害' in header or 'ジャンプ' in header or '芝・ダート' in header or '芝、ダート' in header:
        surface = 'jump'
    going = next((g for g in ('不良', '稍重', '重', '良') if date and re.search(r'(?<!負担)'+g, date[3].split('(')[0])), '')
    try:
        race_date = dt.date(job['year'], int(date[1]), int(date[2])).isoformat() if date else None
        off_timestamp = f'{race_date}T{int(off[1]):02}:{int(off[2]):02}:00+09:00' if date and off else None
    except ValueError:
        race_date = off_timestamp = None
    expected = int(count[1]) if count else None
    if not (1 <= number <= 12):
        issues.append('invalid race number')
    if not race_date or not off_timestamp or not surface or not distance or not going:
        issues.append('incomplete race metadata')
    # Gate and horse-number columns are left-aligned consistently in each panel.
    tops = sorted({round(c['top'], 1) for c in chars if 20 <= c['x0'] < 26 and c['text'].isdigit()})
    runners = []
    for top in tops:
        gate = cell(chars, 20, 26, top)
        horse = cell(chars, 26, 38, top)
        name = compact(cell(chars, 38, 110.5, top))
        sex_age = compact(cell(chars, 110.5, 129, top))
        if not gate.isdigit() or not 1 <= int(gate) <= 8 or not horse.isdigit() or not 1 <= int(horse) <= 18:
            continue
        if not re.search(r'\d', sex_age) or not name:
            continue
        # One candidate per printed row, even if adjacent glyphs differ slightly in height.
        if any(abs(x['_top'] - top) < 2 for x in runners):
            continue
        jockey = compact(cell(chars, 150, 193, top))
        weight = compact(cell(chars, 131, 147, top))
        body = compact(cell(chars, 306, 320.5, top))
        change = compact(cell(chars, 320.5, 334, top))
        result_time = compact(cell(chars, 334, 357, top))
        odds = compact(cell(chars, 380, 405, top))
        odds_match = re.match(r'(\d+\.\d+)', odds)
        odds_value = float(odds_match[1]) if odds_match else None
        if odds_value is None or odds_value < 1:
            issues.append(f'missing/invalid final odds: horse {horse}')
        if '(cid:' in name or '(cid:' in jockey:
            # Store raw evidence but never create an apparently verified identity.
            identity_status = 'unresolved_font_glyph'
        else:
            identity_status = 'names_only_unlinked'
        runners.append({'horse_number': int(horse), 'gate': int(gate), 'horse_name': name,
                        'sex_age': sex_age, 'jockey_name': jockey, 'carried_weight_raw': weight,
                        'body_weight_raw': body, 'body_weight_change_raw': change,
                        'finish_time_raw': result_time, 'final_win_odds': odds_value,
                        'horse_id': None, 'jockey_id': None, 'identity_status': identity_status,
                        'pre_off_odds': None, 'odds_timestamp': None, 'result_available_at': None,
                        '_top': top})
    if expected is None or len(runners) != expected:
        issues.append(f'runner count mismatch: parsed={len(runners)}, expected={expected}')
    numbers = [r['horse_number'] for r in runners]
    if len(set(numbers)) != len(numbers):
        issues.append('duplicate horse numbers')
    if re.search(r'同着|競走中止|出走取消|競走除外|失格|競走取りやめ', text):
        issues.append('exceptional result requires separate rank/cancellation handling')
    payout = re.search(r'単\s*勝\s+(?:\(cid:\d+\)|[①-⑳\d])+\s+([\d,]+)円', text)
    win_payout = int(payout[1].replace(',', '')) if payout else None
    if runners and win_payout is not None and runners[0]['final_win_odds'] is not None:
        if abs(win_payout - runners[0]['final_win_odds'] * 100) > .1:
            issues.append('winner final odds vs official win payout mismatch')
    else:
        issues.append('official win payout unavailable')
    status = 'validated_result' if not issues else 'requires_review'
    for order, runner in enumerate(runners, 1):
        runner['finish_order'] = order
        runner['finish_position'] = order if status == 'validated_result' else None
        del runner['_top']
    meta = {'source_url': job['url'], 'raw_text': text, 'win_payout_100': win_payout,
            'outline_recovered': outline_recovered,
            'historical_features_eligible': False,
            'blockers': ['verified horse/jockey IDs missing', 'result publication timestamp missing'],
            'parser_version': VERSION}
    return {'race_id': race_id, 'document_url': job['url'], 'page_number': page_number,
            'panel': panel, 'race_number': number, 'race_date': race_date,
            'track': VENUES[job['venue']][1], 'surface': surface,
            'distance_m': int(distance[1].replace(',', '')) if distance else None,
            'going': going, 'off_timestamp': off_timestamp, 'expected_runners': expected,
            'status': status, 'issues_json': json.dumps(sorted(set(issues)), ensure_ascii=False),
            'metadata_json': json.dumps(meta, ensure_ascii=False), 'runners': runners}


def parse_document(job):
    races = []
    templates = None
    try:
        with pdfplumber.open(job['local_path']) as pdf:
            for page_number, page in enumerate(pdf.pages, 1):
                width = page.width / 2
                outlined_panels = [len([c for c in page.curves if side*width <= c['x0'] < (side+1)*width]) > 500
                    and sum(c['text'].isdigit() or '(cid:98' in c['text'] for c in page.chars if side*width <= c['x0'] < (side+1)*width) < 200
                    for side in (0, 1)]
                outlined = any(outlined_panels)
                page_chars = page.chars
                if outlined:
                    from outline_digits import font_templates, recover
                    if templates is None:
                        templates = font_templates(job['local_path'])
                    page_chars = page_chars + recover(page, templates)
                # Scale only positions, not font glyph decoding, for varying media boxes.
                for panel in (0, 1):
                    chars = [{**c, 'text': normalize(c['text']),
                              'x0': c['x0'] * 420.945 / width - panel * 410.46,
                              'x1': c['x1'] * 420.945 / width - panel * 410.46}
                             for c in page_chars if panel * width <= c['x0'] < (panel + 1) * width]
                    race = read_panel(chars, job, page_number, panel, outlined_panels[panel])
                    if race:
                        races.append(race)
                page.close()
        ids = [r['race_id'] for r in races]
        if len(set(ids)) != len(ids):
            raise ValueError('duplicate race panels')
        if len(races) != 12 or {r['race_number'] for r in races} != set(range(1, 13)):
            return {'job': job, 'races': races, 'error': f'incomplete daily field: {len(races)}/12 races'}
        return {'job': job, 'races': races, 'error': None}
    except Exception as exc:
        return {'job': job, 'races': [], 'error': str(exc)}


def parse_jobs(db, years=None, review_only=False):
    condition = " AND status='parse_review'" if review_only else ''
    parameters = [VERSION]
    if years is not None:
        if not years or any(type(y) is not int or not 2000 <= y <= 2100 for y in years):
            raise ValueError('valid explicit years required')
        condition += ' AND year IN (' + ','.join('?' for _ in years) + ')'
        parameters.extend(years)
    return [dict(r) for r in db.execute("SELECT * FROM annual_report_documents WHERE local_path IS NOT NULL AND (parser_version IS NULL OR parser_version!=?)" + condition, parameters)]


def ingest(db_path, workers=4, limit=None, review_only=False, years=None):
    if not 1 <= workers <= 4:
        raise ValueError('workers must be 1..4')
    db = connect(db_path)
    db.row_factory = __import__('sqlite3').Row
    jobs = parse_jobs(db, years, review_only)
    if limit:
        jobs = jobs[:limit]
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        for n, result in enumerate(pool.map(parse_document, jobs, chunksize=1), 1):
            job = result['job']
            rows = result['races']
            if result['error']:
                for race in rows:
                    race['status'] = 'requires_review'
                    race['issues_json'] = json.dumps(json.loads(race['issues_json']) + [result['error']], ensure_ascii=False)
                    for runner in race['runners']:
                        runner['finish_position'] = None
            with db:
                old_ids = [r[0] for r in db.execute('SELECT race_id FROM annual_report_races WHERE document_url=?', (job['url'],))]
                for race_id in old_ids:
                    db.execute('DELETE FROM annual_report_runners WHERE race_id=?', (race_id,))
                db.execute('DELETE FROM annual_report_races WHERE document_url=?', (job['url'],))
                for race in rows:
                    db.execute('''INSERT INTO annual_report_races VALUES(:race_id,:document_url,:page_number,:panel,:race_number,
                      :race_date,:track,:surface,:distance_m,:going,:off_timestamp,:expected_runners,:status,:issues_json,:metadata_json)''', race)
                    for runner in race['runners']:
                        db.execute('INSERT INTO annual_report_runners VALUES(?,?,?,?,?,?,?,?)',
                                   (race['race_id'], runner['horse_number'], runner['finish_order'], runner['horse_name'],
                                    runner['jockey_name'], None, None, json.dumps(runner, ensure_ascii=False)))
                status = 'parsed' if not result['error'] else 'parse_review'
                db.execute('''UPDATE annual_report_documents SET status=?,error=?,race_count=?,runner_count=?,parser_version=? WHERE url=?''',
                           (status, result['error'], len(rows), sum(len(r['runners']) for r in rows), VERSION, job['url']))
            if n % 10 == 0 or n == len(jobs):
                print(json.dumps({'parsed_pdfs': n, 'total': len(jobs), 'last_races': len(rows), 'error': result['error']}), flush=True)
    db.close()


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--db', required=True)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--limit', type=int)
    ap.add_argument('--review-only', action='store_true')
    ap.add_argument('--years', type=int, nargs='+', help='Limit parsing to these years; preserve attested earlier years')
    args = ap.parse_args()
    ingest(args.db, args.workers, args.limit, args.review_only, args.years)
