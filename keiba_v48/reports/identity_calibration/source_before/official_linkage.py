"""Evidence-backed JRA entity linkage. Names alone never create official IDs.

Follow only links actually published by JRA, cache source bytes and checksums,
and verify each result row against the annual PDF before using its identity.
"""
import argparse
import collections
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import unicodedata
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup
import requests
from annual_reports import VENUES

BASE = 'https://www.jra.go.jp'
RACE = re.compile(r'pw01sde\d{2}(\d{2})(\d{4})(\d{2})(\d{2})(\d{2})(\d{8})/')
HORSE = re.compile(r'pw01dud\d{2}(\d{10})/')
JOCKEY = re.compile(r'pw04kmk(\d{6})/')
ACTION = re.compile(r"doAction\(['\"](/JRADB/access[SK]\.html)['\"]\s*,\s*['\"]([^'\"]+)['\"]")
_LOCAL = threading.local()


def normalized(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value or ''))


def jockey_name(value):
    # Printed apprentice allowance symbols are not part of the rider's name.
    return normalized(value).lstrip('▲△☆★◇')


def code(url):
    return parse_qs(urlparse(url).query).get('CNAME', [''])[0]


def race_key(url):
    m = RACE.match(code(url))
    if not m:
        return None
    venue, year, meeting, day, race, date = m.groups()
    return year + venue + meeting + day + race, dt.datetime.strptime(date, '%Y%m%d').date().isoformat()


def profile_key(url):
    m = HORSE.match(code(url))
    return 'jra:' + m[1] if m else None


def official_url(url):
    p = urlparse(url)
    if p.scheme != 'https' or p.hostname != 'www.jra.go.jp' or not p.path.startswith(('/JRADB/', '/datafile/', '/keiba/', '/news/')):
        raise ValueError('official JRA HTTPS URL required')
    if p.path.startswith('/JRADB/'):
        return BASE + p.path + '?' + urlencode({'CNAME': code(url)})
    return url


def links(soup, base):
    result = set()
    for a in soup.find_all(['a', 'option']):
        href = a.get('href', '')
        if '/JRADB/accessS.html?CNAME=' in href:
            result.add(official_url(urljoin(base, href)))
        for path, value in ACTION.findall(a.get('onclick', '')):
            result.add(official_url(BASE + path + '?' + urlencode({'CNAME': value})))
    return sorted(result)


def parse_html(raw, parser='html.parser'):
    # JRA declares Shift_JIS but uses CP932 extension glyphs.
    if re.search(br'charset\s*=\s*["\x27]?shift[_-]jis', raw[:1000], re.I):
        raw = raw.decode('cp932')
    return BeautifulSoup(raw, parser)


class SourceCache:
    def __init__(self, folder, parser='html.parser'):
        self.parser = parser
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

    def get(self, url):
        url = official_url(url)
        stem = self.folder / hashlib.sha256(url.encode()).hexdigest()
        raw_path = stem.with_suffix('.html')
        meta_path = stem.with_suffix('.json')
        if raw_path.exists() and meta_path.exists():
            raw = raw_path.read_bytes()
            meta = json.loads(meta_path.read_text())
            if meta['url'] != url or hashlib.sha256(raw).hexdigest() != meta['sha256']:
                raise ValueError('source cache checksum mismatch')
        else:
            if not hasattr(_LOCAL, 'session'):
                _LOCAL.session = requests.Session()
                _LOCAL.session.headers['User-Agent'] = 'KeibaPersonalResearch/4.8'
            response = _LOCAL.session.get(url, timeout=(10, 25), allow_redirects=False)
            if response.status_code != 200:
                errors=self.folder/'request_errors';errors.mkdir(exist_ok=True)
                location=response.headers.get('Location')
                (errors/(stem.name+'.json')).write_text(json.dumps(dict(url=url,status=response.status_code,
                    location=location if isinstance(location,str) else None,observed_at=dt.datetime.now(dt.timezone.utc).isoformat(),redirect_followed=False)))
            if response.status_code in (401, 403, 429):
                raise PermissionError(f'source refused request ({response.status_code}): {url}')
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError('unexpected response status')
            raw = response.content
            meta = dict(url=url, sha256=hashlib.sha256(raw).hexdigest(),
                        observed_at=dt.datetime.now(dt.timezone.utc).isoformat())
            raw_path.write_bytes(raw)
            meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
        return parse_html(raw, self.parser), meta


def parse_result(soup, url):
    key = race_key(url)
    if not key:
        return []
    race_id, date = key
    table = soup.select_one('table.basic.narrow-xy')
    if table is None:
        raise ValueError('result table unavailable')
    header = table.select_one('.date_line .date')
    printed = re.search(r'(\d{4})年(\d+)月(\d+)日', header.get_text() if header else '')
    if not printed or dt.date(*map(int, printed.groups())).isoformat() != date:
        raise ValueError('source date disagrees with result URL')
    meeting = re.search(r'(\d+)回(札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉)(\d+)日', normalized(header.get_text()))
    parts = RACE.match(code(url))
    venue_name = next((v[1] for v in VENUES.values() if v[0] == parts[1]), None)
    if not meeting or (int(meeting[1]),meeting[2],int(meeting[3])) != (int(parts[3]),venue_name,int(parts[4])):
        raise ValueError('source meeting/venue/day disagrees with result URL')
    time_cell = table.select_one('.date_line .time')
    time = re.search(r'(\d+)時(\d+)分', normalized(time_cell.get_text()) if time_cell else '')
    displayed_off = f'{date}T{int(time[1]):02}:{int(time[2]):02}:00+09:00' if time else None
    race_image = table.select_one('.race_number img[alt]')
    if not race_image or race_image['alt'] != str(int(race_id[-2:])) + 'レース':
        raise ValueError('source race number disagrees with result URL')
    output = []
    for tr in table.select('tbody > tr'):
        horse = tr.select_one('td.horse a[href]')
        jockey_cell = tr.select_one('td.jockey')
        jockey = tr.select_one('td.jockey a[onclick]')
        number = tr.select_one('td.num')
        age = tr.select_one('td.age')
        if not horse or not number or not age:
            continue
        hm = HORSE.search(unquote(horse.get('href', '')))
        jm = JOCKEY.search(jockey.get('onclick', '')) if jockey else None
        am = re.search(r'(\d+)', normalized(age.get_text()))
        if not hm or not am or not number.get_text(strip=True).isdigit():
            continue
        birth = int(date[:4]) - int(am[1])
        if int(hm[1][:4]) != birth:
            raise ValueError('horse registration year disagrees with age')
        output.append(dict(race_id=race_id, race_date=date,
                           horse_number=int(number.get_text(strip=True)),
                           horse_name=normalized(horse.get_text()), birth_year=birth,
                           horse_id='jra:' + hm[1],
                           jockey_name=jockey_name(jockey_cell.get_text()) if jockey_cell else None,
                           jockey_id='jra:' + jm[1] if jm else None,
                           source_finish_position=int(tr.select_one('td.place').get_text(strip=True))
                               if tr.select_one('td.place') and tr.select_one('td.place').get_text(strip=True).isdigit() else None,
                           result_page_off_at=displayed_off,
                           horse_profile_url=urljoin(BASE, horse['href'])))
    if not output or len({r['horse_number'] for r in output}) != len(output):
        raise ValueError('empty or duplicate source field')
    return output


def parse_profile_starts(soup, url):
    """Parse start-level identity evidence from a cached official horse page.

    A profile URL proves the horse registration code.  Each accepted row also
    carries an official result URL, printed date, and rider link; callers must
    still match it to one annual-report row before propagation.
    """
    horse_id = profile_key(url)
    if not horse_id:
        return []
    output = []
    for tr in soup.select('tbody > tr'):
        race = tr.select_one('td.race a[href*="pw01sde"]')
        jockey_cell = tr.select_one('td.jockey')
        jockey = tr.select_one('td.jockey a[onclick*="pw04kmk"]')
        date_cell = tr.select_one('td.date')
        if not race or not jockey or not date_cell:
            continue
        result_url = official_url(urljoin(BASE, race['href']))
        key = race_key(result_url)
        jm = JOCKEY.search(jockey.get('onclick', ''))
        printed = re.search(r'(\d{4})年(\d+)月(\d+)日', normalized(date_cell.get_text()))
        if not key or not jm or not printed:
            continue
        printed_date = dt.date(*map(int, printed.groups())).isoformat()
        if printed_date != key[1]:
            raise ValueError('profile start date disagrees with result URL')
        output.append(dict(profile_horse_id=horse_id, race_id=key[0], race_date=key[1],
                           jockey_name=jockey_name(jockey_cell.get_text()),
                           jockey_id='jra:' + jm[1], result_url=result_url))
    if len({r['race_id'] for r in output}) != len(output):
        raise ValueError('duplicate race in horse profile')
    return output


def schema(db):
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS official_identity_evidence(
      race_id TEXT NOT NULL,horse_number INTEGER NOT NULL,horse_name TEXT NOT NULL,
      birth_year INTEGER NOT NULL,horse_id TEXT NOT NULL,jockey_name TEXT,jockey_id TEXT,
      source_url TEXT NOT NULL,source_sha256 TEXT NOT NULL,observed_at TEXT NOT NULL,
      payload_json TEXT NOT NULL,PRIMARY KEY(race_id,horse_number));
    CREATE TABLE IF NOT EXISTS official_linkage_pages(
      source_url TEXT PRIMARY KEY,source_sha256 TEXT,observed_at TEXT,
      status TEXT NOT NULL,error TEXT,matched_rows INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS annual_time_evidence(
      race_id TEXT PRIMARY KEY,scheduled_off_at TEXT,actual_off_at TEXT,
      result_published_at TEXT,result_first_observed_at TEXT,
      publication_policy_url TEXT NOT NULL,publication_time_basis TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS official_jockey_aliases(
      alias TEXT PRIMARY KEY,canonical_name TEXT,jockey_id TEXT,supporting_races INTEGER NOT NULL,
      status TEXT NOT NULL,evidence_race_id TEXT,evidence_horse_number INTEGER,details_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS official_profile_start_evidence(
      race_id TEXT NOT NULL,horse_number INTEGER NOT NULL,profile_horse_id TEXT NOT NULL,
      horse_name TEXT NOT NULL,race_date TEXT NOT NULL,jockey_name TEXT NOT NULL,jockey_id TEXT NOT NULL,
      source_url TEXT NOT NULL,source_sha256 TEXT NOT NULL,observed_at TEXT NOT NULL,payload_json TEXT NOT NULL,
      PRIMARY KEY(race_id,horse_number),
      FOREIGN KEY(race_id,horse_number) REFERENCES annual_report_runners(race_id,horse_number) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS annual_identity_links(
      race_id TEXT NOT NULL,horse_number INTEGER NOT NULL,horse_id TEXT,jockey_id TEXT,
      horse_match_method TEXT,jockey_match_method TEXT,
      horse_evidence_race_id TEXT,horse_evidence_horse_number INTEGER,
      jockey_evidence_race_id TEXT,jockey_evidence_horse_number INTEGER,
      PRIMARY KEY(race_id,horse_number),
      FOREIGN KEY(race_id,horse_number) REFERENCES annual_report_runners(race_id,horse_number) ON DELETE CASCADE,
      FOREIGN KEY(horse_evidence_race_id,horse_evidence_horse_number)
        REFERENCES official_identity_evidence(race_id,horse_number),
      FOREIGN KEY(jockey_evidence_race_id,jockey_evidence_horse_number)
        REFERENCES official_identity_evidence(race_id,horse_number));
    ''')
    columns = {r[1] for r in db.execute('PRAGMA table_info(annual_time_evidence)')}
    for column in ('result_page_off_at', 'result_page_source_url', 'result_page_source_sha256'):
        if column not in columns:
            db.execute('ALTER TABLE annual_time_evidence ADD COLUMN ' + column + ' TEXT')
    db.commit()


def attest(db, rows, meta):
    accepted = 0
    for row in rows:
        target = db.execute('''SELECT r.race_date,h.horse_name,h.payload_json,r.off_timestamp
            FROM annual_report_races r JOIN annual_report_runners h USING(race_id)
            WHERE r.race_id=? AND h.horse_number=?''', (row['race_id'], row['horse_number'])).fetchone()
        if not target:
            continue
        payload = json.loads(target[2])
        age = re.search(r'(\d+)', payload.get('sex_age', ''))
        if (target[0] != row['race_date'] or normalized(target[1]) != row['horse_name'] or
                not age or int(target[0][:4]) - int(age[1]) != row['birth_year']):
            continue
        # A conflicting previously attested source is a hard error, not last-write-wins.
        old = db.execute('SELECT horse_id,jockey_id FROM official_identity_evidence WHERE race_id=? AND horse_number=?',
                         (row['race_id'], row['horse_number'])).fetchone()
        if old and (old[0] != row['horse_id'] or old[1] != row['jockey_id']):
            raise ValueError('conflicting identity evidence')
        db.execute('INSERT OR IGNORE INTO official_identity_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                   (row['race_id'], row['horse_number'], row['horse_name'], row['birth_year'],
                    row['horse_id'], row['jockey_name'], row['jockey_id'],
                    meta['url'], meta['sha256'], meta['observed_at'], json.dumps(row, ensure_ascii=False)))
        if old:
            db.execute('UPDATE official_identity_evidence SET payload_json=? WHERE race_id=? AND horse_number=?',
                       (json.dumps(row, ensure_ascii=False), row['race_id'], row['horse_number']))
        accepted += 1
    return accepted


def attest_profile_starts(db, rows, meta):
    """Match profile starts only by race plus an already attested horse name.

    This deliberately does not create a global name-only identity.  The horse
    code must already have independent result-page evidence and the profile
    start must identify exactly one same-name annual row in the same race.
    """
    accepted = 0
    for row in rows:
        identities = db.execute('''SELECT DISTINCT horse_name,birth_year FROM official_identity_evidence
            WHERE horse_id=?''', (row['profile_horse_id'],)).fetchall()
        if len(identities) != 1:
            continue
        official_name = normalized(identities[0][0])
        race = db.execute('SELECT race_date FROM annual_report_races WHERE race_id=?', (row['race_id'],)).fetchone()
        if not race or (race[0] is not None and race[0] != row['race_date']):
            continue
        candidates = []
        for target in db.execute('''SELECT horse_number,horse_name,jockey_name,horse_id,jockey_id
                FROM annual_report_runners WHERE race_id=?''', (row['race_id'],)):
            if normalized(target[1]) == official_name:
                candidates.append(target)
        if len(candidates) != 1:
            continue
        number, horse_name_raw, jockey_name_raw, old_hid, old_jid = candidates[0]
        if jockey_name(jockey_name_raw) != jockey_name(row['jockey_name']):
            continue
        if old_hid not in (None, row['profile_horse_id']) or old_jid not in (None, row['jockey_id']):
            raise ValueError('profile identity conflicts with linked annual row')
        old = db.execute('''SELECT profile_horse_id,jockey_id FROM official_profile_start_evidence
            WHERE race_id=? AND horse_number=?''', (row['race_id'], number)).fetchone()
        if old and (old[0] != row['profile_horse_id'] or old[1] != row['jockey_id']):
            raise ValueError('conflicting profile start evidence')
        payload = dict(row, horse_number=number, horse_name=horse_name_raw)
        db.execute('INSERT OR REPLACE INTO official_profile_start_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                   (row['race_id'], number, row['profile_horse_id'], horse_name_raw, row['race_date'],
                    row['jockey_name'], row['jockey_id'], meta['url'], meta['sha256'], meta['observed_at'],
                    json.dumps(payload, ensure_ascii=False)))
        accepted += 1
    return accepted


def propagate(db):
    horses, jockeys = collections.defaultdict(set), collections.defaultdict(set)
    horse_proof, jockey_proof = {}, {}
    direct = {}
    for rid, num, hid, jid, name, birth in db.execute('SELECT race_id,horse_number,horse_id,jockey_id,horse_name,birth_year FROM official_identity_evidence'):
        direct[rid, num] = (hid, jid, name, birth)
    profile_direct = {(rid, num): (hid, jid) for rid, num, hid, jid in db.execute(
        'SELECT race_id,horse_number,profile_horse_id,jockey_id FROM official_profile_start_evidence')}
    query = '''SELECT race_id,horse_number,horse_name,birth_year,horse_id,jockey_name,jockey_id
        FROM official_identity_evidence ORDER BY race_id,horse_number'''
    for rid, num, name, birth, hid, jname, jid in db.execute(query):
        horses[name, birth].add(hid)
        horse_proof.setdefault((name, birth, hid), (rid, num))
        if jid and jname:
            jockeys[jockey_name(jname)].add(jid)
            jockey_proof.setdefault((jockey_name(jname), jid), (rid, num))
    aliases = collections.defaultdict(list)
    alias_query = '''SELECT e.race_id,e.horse_number,h.jockey_name,e.payload_json,e.jockey_id,h.horse_name,h.payload_json,r.race_date,e.horse_name,e.birth_year
        FROM official_identity_evidence e JOIN annual_report_runners h USING(race_id,horse_number)
        JOIN annual_report_races r USING(race_id)
        ORDER BY e.race_id,e.horse_number'''
    for rid,num,raw,payload,jid,hname,hpayload,date,source_name,source_birth in db.execute(alias_query):
        proof_row=json.loads(payload);age=re.search(r'(\d+)',json.loads(hpayload).get('sex_age',''))
        if not age or not date or normalized(hname)!=source_name or int(date[:4])-int(age[1])!=source_birth:
            continue
        canonical = jockey_name(json.loads(payload).get('jockey_name'))
        alias = jockey_name(raw)
        if alias and canonical and alias != canonical:
            aliases[alias].append((canonical,jid,rid,num))
    alias_proofs = {}
    for alias, evidence_rows in aliases.items():
        names = {r[0] for r in evidence_rows}
        ids = {r[1] for r in evidence_rows if r[1]}
        support = len({r[2] for r in evidence_rows if r[1]})
        accepted = len(names) == 1 and len(ids) == 1 and support >= 3
        proof = next((r for r in evidence_rows if r[1]), evidence_rows[0])
        if accepted:
            jid = next(iter(ids))
            jockeys[alias].add(jid)
            jockey_proof[alias,jid] = (proof[2],proof[3])
            alias_proofs[alias] = (proof[2],proof[3])
        db.execute('INSERT OR REPLACE INTO official_jockey_aliases VALUES(?,?,?,?,?,?,?,?)',
                   (alias,next(iter(names)) if len(names)==1 else None,next(iter(ids)) if accepted else None,
                    support,'attested' if accepted else 'ambiguous_or_insufficient',
                    proof[2],proof[3],json.dumps({'observed_names':sorted(names),'observed_ids':sorted(ids)},ensure_ascii=False)))
    changes, lineage = [], []
    counts = collections.Counter()
    query = '''SELECT h.race_id,h.horse_number,h.horse_name,h.jockey_name,h.payload_json,r.race_date
        FROM annual_report_runners h JOIN annual_report_races r USING(race_id)'''
    for rid, num, hname, jname, payload, date in db.execute(query):
        row = json.loads(payload)
        age = re.search(r'(\d+)', row.get('sex_age', ''))
        birth = int(date[:4]) - int(age[1]) if date and age else None
        hs = horses.get((normalized(hname), birth), set())
        js = jockeys.get(jockey_name(jname), set())
        hid = next(iter(hs)) if len(hs) == 1 else None
        jid = next(iter(js)) if len(js) == 1 else None
        evidence = direct.get((rid, num))
        if evidence and (evidence[2] != normalized(hname) or evidence[3] != birth):
            evidence = None  # source-row attestation is stale after an annual reparse
        if evidence:
            # The exact source row was independently attested against horse
            # number/name/birth year. This also handles damaged PDF rider glyphs
            # without introducing fuzzy global name aliases.
            hid, jid = evidence[:2]
            counts['direct_source_row_linked'] += bool(hid and jid)
        profile_evidence = profile_direct.get((rid, num)) if not evidence else None
        if profile_evidence:
            hid, jid = profile_evidence
            counts['profile_source_row_linked'] += bool(hid and jid)
        hp = (rid, num) if evidence and hid else horse_proof.get((normalized(hname), birth, hid), (None, None))
        jp = (rid, num) if evidence and jid else jockey_proof.get((jockey_name(jname), jid), (None, None))
        lineage.append((rid,num,hid,jid,
                        'exact_source_race_and_runner' if evidence and hid else
                        'exact_profile_start_and_attested_horse' if profile_evidence and hid else
                        'exact_name_and_birth_year' if hid else None,
                        'exact_source_race_and_runner' if evidence and jid else
                        'exact_profile_start_and_attested_horse' if profile_evidence and jid else
                        'multi_race_attested_pdf_alias' if jid and jockey_name(jname) in alias_proofs else 'unique_official_name' if jid else None,
                        *hp,*jp))
        status = 'official_ids_linked' if hid and jid else 'partially_linked' if hid or jid else ('unresolved_font_glyph' if '(cid:' in hname else 'names_only_unlinked')
        row.update(horse_id=hid, jockey_id=jid, identity_status=status)
        changes.append((hid, jid, json.dumps(row, ensure_ascii=False), rid, num))
        counts['horse_linked_rows'] += bool(hid)
        counts['jockey_linked_rows'] += bool(jid)
        counts['both_linked_rows'] += bool(hid and jid)
    db.executemany('UPDATE annual_report_runners SET horse_id=?,jockey_id=?,payload_json=? WHERE race_id=? AND horse_number=?', changes)
    db.executemany('INSERT OR REPLACE INTO annual_identity_links VALUES(?,?,?,?,?,?,?,?,?,?)', lineage)
    db.execute('''INSERT INTO annual_time_evidence
      (race_id,scheduled_off_at,actual_off_at,result_published_at,result_first_observed_at,
       publication_policy_url,publication_time_basis)
      SELECT r.race_id,r.off_timestamp,NULL,NULL,d.fetched_at,
        'https://www.jra.go.jp/datafile/seiseki/report/',
        'scheduled_off_from_report; publication_exact_unknown; observation_is_current_fetch'
      FROM annual_report_races r JOIN annual_report_documents d ON d.url=r.document_url WHERE 1
      ON CONFLICT(race_id) DO UPDATE SET scheduled_off_at=excluded.scheduled_off_at,
        result_first_observed_at=CASE
          WHEN annual_time_evidence.result_first_observed_at IS NULL
            OR julianday(excluded.result_first_observed_at) < julianday(annual_time_evidence.result_first_observed_at)
          THEN excluded.result_first_observed_at ELSE annual_time_evidence.result_first_observed_at END''')
    displayed_times = db.execute('''SELECT race_id,json_extract(payload_json,'$.result_page_off_at'),
        source_url,source_sha256 FROM official_identity_evidence
        WHERE json_extract(payload_json,'$.result_page_off_at') IS NOT NULL GROUP BY race_id''').fetchall()
    db.executemany('''UPDATE annual_time_evidence SET result_page_off_at=?,result_page_source_url=?,
        result_page_source_sha256=? WHERE race_id=?''', [(at,url,sha,rid) for rid,at,url,sha in displayed_times])
    counts['distinct_attested_horses'] = db.execute('SELECT count(DISTINCT horse_id) FROM official_identity_evidence').fetchone()[0]
    counts['distinct_attested_jockeys'] = db.execute('SELECT count(DISTINCT jockey_id) FROM official_identity_evidence').fetchone()[0]
    counts['ambiguous_horse_keys'] = sum(len(s) > 1 for s in horses.values())
    counts['ambiguous_jockey_names'] = sum(len(s) > 1 for s in jockeys.values())
    counts['strict_historical_publication_verified_rows'] = 0
    counts['attested_pdf_jockey_aliases'] = len(alias_proofs)
    return dict(counts)


def audit(db):
    return {
        'source_attested_rows': db.execute('SELECT count(*) FROM official_identity_evidence').fetchone()[0],
        'profile_start_attested_rows': db.execute('SELECT count(*) FROM official_profile_start_evidence').fetchone()[0],
        'profile_start_distinct_horses': db.execute('SELECT count(DISTINCT profile_horse_id) FROM official_profile_start_evidence').fetchone()[0],
        'page_statuses': dict(db.execute('SELECT status,count(*) FROM official_linkage_pages GROUP BY status')),
        'source_errors': [dict(url=u,error=e) for u,e in db.execute("SELECT source_url,error FROM official_linkage_pages WHERE status='error'")],
        'rank_disagreements': db.execute('''SELECT count(*) FROM official_identity_evidence e
            JOIN annual_report_runners h USING(race_id,horse_number)
            JOIN annual_report_races r USING(race_id) WHERE r.status='validated_result'
            AND json_extract(e.payload_json,'$.source_finish_position') != json_extract(h.payload_json,'$.finish_position')''').fetchone()[0],
        'linked_rows_by_year': [dict(year=y,rows=n,horse_linked=h,jockey_linked=j,both_linked=b)
            for y,n,h,j,b in db.execute('''SELECT substr(race_id,1,4),count(*),sum(horse_id IS NOT NULL),
                sum(jockey_id IS NOT NULL),sum(horse_id IS NOT NULL AND jockey_id IS NOT NULL)
                FROM annual_report_runners GROUP BY 1 ORDER BY 1''')],
        'unlinked_jockey_names': [dict(name=n,rows=c) for n,c in db.execute('''SELECT jockey_name,count(*)
            FROM annual_report_runners WHERE jockey_id IS NULL GROUP BY jockey_name ORDER BY count(*) DESC LIMIT 30''')],
        'time_evidence_rows': db.execute('SELECT count(*) FROM annual_time_evidence').fetchone()[0],
        'result_page_off_times_recorded': db.execute('SELECT count(*) FROM annual_time_evidence WHERE result_page_off_at IS NOT NULL').fetchone()[0],
        'pdf_vs_result_page_off_differences': [dict(race_id=rid,pdf_scheduled_off_at=a,result_page_off_at=b)
            for rid,a,b in db.execute('''SELECT race_id,scheduled_off_at,result_page_off_at FROM annual_time_evidence
              WHERE scheduled_off_at != result_page_off_at ORDER BY race_id''')],
        'verified_exact_publication_times': db.execute('SELECT count(*) FROM annual_time_evidence WHERE result_published_at IS NOT NULL').fetchone()[0],
        'integrity_check': db.execute('PRAGMA integrity_check').fetchone()[0],
        'foreign_key_violations': len(db.execute('PRAGMA foreign_key_check').fetchall()),
    }


def unlinked_causes(db):
    observed_riders = collections.defaultdict(set)
    for payload, jid in db.execute('SELECT payload_json,jockey_id FROM official_identity_evidence'):
        name=jockey_name(json.loads(payload).get('jockey_name'))
        if name:
            observed_riders[name].add(jid)
    aliases={a:s for a,s in db.execute('SELECT alias,status FROM official_jockey_aliases')}
    horse_counts,jockey_counts=collections.Counter(),collections.Counter()
    for hname,jname,hid,jid,payload,date in db.execute('''SELECT h.horse_name,h.jockey_name,h.horse_id,h.jockey_id,h.payload_json,r.race_date
        FROM annual_report_runners h JOIN annual_report_races r USING(race_id)'''):
        if not hid:
            p=json.loads(payload)
            cause=('unresolved_pdf_glyph' if '(cid:' in hname else
                   'missing_birth_year' if not date or not re.search(r'\d+',p.get('sex_age','')) else
                   'no_unique_attested_name_birth_key')
            horse_counts[cause]+=1
        if not jid:
            name=jockey_name(jname)
            cause=('ambiguous_or_insufficient_pdf_alias' if name in aliases and aliases[name]!='attested' else
                   'official_result_has_name_but_no_code' if name in observed_riders and not any(observed_riders[name]) else
                   'unresolved_pdf_glyph' if '(cid:' in name else 'no_attested_source_code')
            jockey_counts[cause]+=1
    return dict(horse_unlinked=dict(horse_counts),jockey_unlinked=dict(jockey_counts),
                total_horse_unlinked=sum(horse_counts.values()),total_jockey_unlinked=sum(jockey_counts.values()),
                alias_decisions=[dict(alias=a,canonical_name=n,jockey_id=i,supporting_races=c,status=s)
                    for a,n,i,c,s in db.execute('SELECT alias,canonical_name,jockey_id,supporting_races,status FROM official_jockey_aliases ORDER BY alias')])


def rebuild_from_cache(base_path, destination, cache_path):
    """Build on a verified archive in memory, then publish one closed DB snapshot.

    Long-lived file writes are avoided in workspaces that replace idle files.
    The input archive is read-only and the destination must be a new path.
    """
    dest=Path(destination)
    if dest.exists():
        raise ValueError('rebuild destination must not already exist')
    source=sqlite3.connect('file:'+str(Path(base_path).resolve())+'?mode=ro',uri=True)
    if source.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
        source.close();raise ValueError('base archive failed integrity check')
    db=sqlite3.connect(':memory:');source.backup(db);source.close();schema(db)
    cache=SourceCache(cache_path)
    meta_paths=sorted(Path(cache_path).glob('*.json'))
    seen=0
    for path in meta_paths:
        meta=json.loads(path.read_text())
        url=meta.get('url','')
        if not race_key(url):
            continue
        if not path.with_suffix('.html').is_file():
            raise ValueError('offline rebuild source bytes missing')
        soup,meta=cache.get(url)
        try:
            rows=parse_result(soup,url)
            with db:
                matched=attest(db,rows,meta)
                db.execute('INSERT OR REPLACE INTO official_linkage_pages VALUES(?,?,?,?,?,?)',
                           (url,meta['sha256'],meta['observed_at'],'matched',None,matched))
        except ValueError as exc:
            if 'conflicting identity' in str(exc):
                raise
            with db:
                db.execute('INSERT OR REPLACE INTO official_linkage_pages(source_url,status,error) VALUES(?,?,?)',
                           (url,'error',str(exc)))
        seen+=1
        if seen%100==0:print(json.dumps({'cached_pages':seen}),flush=True)
    with db:report=propagate(db)
    report.update(audit(db));report['unlinked_causes']=unlinked_causes(db)
    if report['integrity_check']!='ok' or report['foreign_key_violations']:
        raise ValueError('rebuilt archive failed verification')
    dest.parent.mkdir(parents=True,exist_ok=True)
    staging=dest.with_suffix('.staging.sqlite')
    if staging.exists():
        raise ValueError('staging path already exists')
    target=sqlite3.connect(staging);db.backup(target);target.close();db.close()
    checked=sqlite3.connect('file:'+str(staging.resolve())+'?mode=ro',uri=True)
    if checked.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
        checked.close();raise ValueError('written snapshot failed integrity check')
    checked.close();staging.replace(dest)
    return report


def crawl(db_path, cache_path, seeds, max_pages=240, workers=3):
    if not 1 <= workers <= 4 or max_pages < 1:
        raise ValueError('workers 1..4 and positive page budget required')
    db = sqlite3.connect(db_path)
    schema(db)
    db.close()
    cache = SourceCache(cache_path)
    queues = collections.defaultdict(collections.deque)
    seen = set()
    for url in seeds:
        key = race_key(url)
        if not key:
            raise ValueError('result seed URL required')
        queues[key[1][:4]].append(official_url(url))
    n = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        while n < max_pages and any(queues.values()):
            batch = []
            # Round-robin years prevents a truncated crawl from selecting only one period.
            for year in sorted(queues):
                while queues[year] and queues[year][0] in seen:
                    queues[year].popleft()
                if queues[year] and len(batch) < workers and n + len(batch) < max_pages:
                    url = queues[year].popleft(); seen.add(url); batch.append(url)
            if not batch:
                break
            futures = [(url, pool.submit(cache.get, url)) for url in batch]
            for url, future in futures:
                try:
                    soup, meta = future.result()
                    rows = parse_result(soup, url)
                    # Keep a connection only during a short transaction; a
                    # workspace may replace an idle file between tool calls.
                    db = sqlite3.connect(db_path)
                    try:
                        with db:
                            matched = attest(db, rows, meta)
                            db.execute('INSERT OR REPLACE INTO official_linkage_pages VALUES(?,?,?,?,?,?)',
                                       (url, meta['sha256'], meta['observed_at'], 'matched', None, matched))
                    finally:
                        db.close()
                    for link in links(soup, url):
                        key = race_key(link)
                        if key and key[1][:4] in queues and link not in seen:
                            queues[key[1][:4]].append(link)
                except PermissionError:
                    raise
                except (ValueError, requests.RequestException) as exc:
                    db = sqlite3.connect(db_path)
                    try:
                        with db:
                            db.execute('INSERT OR REPLACE INTO official_linkage_pages(source_url,status,error) VALUES(?,?,?)',
                                       (url, 'error', str(exc)))
                    finally:
                        db.close()
                n += 1
            if n % 15 == 0 or not any(queues.values()) or n == max_pages:
                db = sqlite3.connect(db_path)
                attested_count = db.execute('SELECT count(*) FROM official_identity_evidence').fetchone()[0]
                db.close()
                print(json.dumps({'pages_this_run': n, 'queue': {y: len(q) for y,q in queues.items()},
                                  'attested_rows': attested_count}), flush=True)
    db = sqlite3.connect(db_path)
    with db:
        report = propagate(db)
    report['pages_this_run'] = n
    report.update(audit(db))
    db.close()
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', required=True); p.add_argument('--cache', required=True)
    p.add_argument('--seed', action='append')
    p.add_argument('--seed-file', help='JSON list of source-attested JRA result URLs')
    p.add_argument('--refresh-links-only', action='store_true', help='rebuild derived links and audit without network')
    p.add_argument('--rebuild-from',help='verified read-only base archive; rebuild all cached results into a new --db path')
    p.add_argument('--max-pages', type=int, default=240); p.add_argument('--workers', type=int, default=3)
    p.add_argument('--report', required=True)
    a = p.parse_args()
    if a.rebuild_from:
        result=rebuild_from_cache(a.rebuild_from,a.db,a.cache)
    elif a.refresh_links_only:
        db = sqlite3.connect(a.db); schema(db)
        with db:
            result = propagate(db)
        result.update(audit(db)); db.close()
    else:
        seeds = (a.seed or []) + (json.loads(Path(a.seed_file).read_text()) if a.seed_file else [])
        if not seeds:
            p.error('--seed or --seed-file required')
        result = crawl(a.db, a.cache, seeds, a.max_pages, a.workers)
    Path(a.report).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
