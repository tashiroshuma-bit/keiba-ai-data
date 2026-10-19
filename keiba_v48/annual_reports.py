"""Resumable official ALL-race report archive (distinct from graded-race PDFs).

Only source-attested results are stored; no horse/jockey IDs or pre-off odds
are manufactured. The original archive's tables are never overwritten.
"""
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import re
import sqlite3
import ssl
import threading
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import requests

BASE = 'https://www.jra.go.jp/datafile/seiseki/report/'
_SESSIONS = threading.local()
VENUES = {'sapporo': ('01', '札幌'), 'hakodate': ('02', '函館'),
          'fukushima': ('03', '福島'), 'niigata': ('04', '新潟'),
          'tokyo': ('05', '東京'), 'nakayama': ('06', '中山'),
          'chukyo': ('07', '中京'), 'kyoto': ('08', '京都'),
          'hanshin': ('09', '阪神'), 'kokura': ('10', '小倉')}


def fetch(url):
    if urlparse(url).scheme != 'https' or urlparse(url).hostname != 'www.jra.go.jp':
        raise ValueError('official HTTPS source required')
    if not hasattr(_SESSIONS, 'session'):
        _SESSIONS.session = requests.Session()
        _SESSIONS.session.headers.update({'User-Agent': 'KeibaPersonalResearch/4.8'})
    response = _SESSIONS.session.get(url, timeout=35, verify=ssl.get_default_verify_paths().cafile or True)
    response.raise_for_status()
    return response.content


def discover(html, year):
    jobs = {}
    for anchor in BeautifulSoup(html, 'html.parser').find_all('a', href=True):
        url = urljoin(BASE + f'{year}.html', anchor['href'])
        match = re.fullmatch(r'(\d{4})-(\d+)([a-z]+)(\d+)\.pdf', Path(urlparse(url).path).name)
        if not match or int(match[1]) != year:
            continue
        _, meeting, venue, day = match.groups()
        if venue not in VENUES or urlparse(url).hostname != 'www.jra.go.jp':
            raise ValueError('unrecognized report URL')
        jobs[url] = dict(url=url, year=year, venue=venue, meeting=int(meeting), day=int(day))
    if not jobs:
        raise ValueError(f'no official annual PDF links for {year}')
    return list(jobs.values())


def connect(path):
    db = sqlite3.connect(path)
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS annual_report_documents(
      url TEXT PRIMARY KEY, year INTEGER NOT NULL, venue TEXT NOT NULL,
      meeting INTEGER NOT NULL, day INTEGER NOT NULL, local_path TEXT,
      sha256 TEXT, byte_count INTEGER, fetched_at TEXT, status TEXT NOT NULL,
      error TEXT, extracted_text TEXT, race_count INTEGER, runner_count INTEGER,
      parser_version TEXT);
    CREATE TABLE IF NOT EXISTS annual_report_races(
      race_id TEXT PRIMARY KEY, document_url TEXT NOT NULL REFERENCES annual_report_documents(url),
      page_number INTEGER NOT NULL, panel INTEGER NOT NULL, race_number INTEGER NOT NULL,
      race_date TEXT, track TEXT, surface TEXT, distance_m INTEGER, going TEXT,
      off_timestamp TEXT, expected_runners INTEGER, status TEXT NOT NULL,
      issues_json TEXT NOT NULL, metadata_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS annual_report_runners(
      race_id TEXT NOT NULL REFERENCES annual_report_races(race_id), horse_number INTEGER NOT NULL,
      finish_order INTEGER NOT NULL, horse_name TEXT, jockey_name TEXT,
      horse_id TEXT, jockey_id TEXT, payload_json TEXT NOT NULL,
      PRIMARY KEY(race_id,horse_number));
    ''')
    return db


def download(job, folder):
    path = Path(folder) / str(job['year']) / Path(urlparse(job['url']).path).name
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        cached = path.exists()
        raw = path.read_bytes() if cached else fetch(job['url'])
        if not raw.startswith(b'%PDF-'):
            raise ValueError('invalid PDF signature')
        if not cached:
            temp = path.with_suffix('.part')
            temp.write_bytes(raw)
            temp.replace(path)
        return {**job, 'local_path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                'byte_count': len(raw), 'fetched_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                'status': 'downloaded', 'error': None}
    except Exception as exc:
        return {**job, 'status': 'download_error', 'error': str(exc)}


def collect(db_path, folder, years=(2023, 2024, 2025), workers=4):
    if not 1 <= workers <= 4:
        raise ValueError('workers must be 1..4')
    db = connect(db_path)
    jobs = []
    for year in years:
        ipath = Path(folder) / f'{year}.html'
        ipath.parent.mkdir(parents=True, exist_ok=True)
        html = ipath.read_bytes() if ipath.exists() else fetch(BASE + f'{year}.html')
        if not ipath.exists():
            ipath.write_bytes(html)
        found = discover(html, year)
        for job in found:
            db.execute('''INSERT INTO annual_report_documents(url,year,venue,meeting,day,status)
              VALUES(:url,:year,:venue,:meeting,:day,'indexed') ON CONFLICT(url) DO NOTHING''', job)
        db.commit()
        jobs.extend(found)
        print(json.dumps({'year': year, 'indexed_pdfs': len(found)}), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(download, job, folder): job for job in jobs}
        for n, future in enumerate(concurrent.futures.as_completed(futures), 1):
            item = future.result()
            if item['status'] == 'downloaded':
                db.execute('''UPDATE annual_report_documents SET local_path=:local_path,
                  sha256=:sha256,byte_count=:byte_count,fetched_at=COALESCE(fetched_at,:fetched_at),
                  status=CASE WHEN parser_version IS NULL THEN 'downloaded' ELSE status END,error=NULL WHERE url=:url''', item)
            else:
                db.execute('UPDATE annual_report_documents SET status=:status,error=:error WHERE url=:url', item)
            db.commit()
            if n % 20 == 0 or item['status'] != 'downloaded' or n == len(jobs):
                print(json.dumps({'completed': n, 'total': len(jobs), 'last_status': item['status'], 'error': item.get('error')}), flush=True)
    result = dict(db.execute('SELECT status,count(*) FROM annual_report_documents GROUP BY status').fetchall())
    db.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--cache', required=True)
    parser.add_argument('--years', type=int, nargs='+', default=[2023, 2024, 2025])
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    print(json.dumps(collect(args.db, args.cache, args.years, args.workers), ensure_ascii=False))


if __name__ == '__main__':
    main()
