"""Verify a Library readback against the pre-upload checkpoint and prior history."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import zipfile
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'keiba_v48'))
from annual_year_update import digest, raw_history_digest
from integrated_data_audit import audit_database


def verify(database, archive, baseline, checkpoint):
    database, archive, baseline = map(Path, (database, archive, baseline))
    expected = json.loads(Path(checkpoint).read_text())
    identities = {}
    for name, path in (('database', database), ('originals', archive)):
        identity = dict(sha256=digest(path), bytes=path.stat().st_size,
                        library_file_id=os.getxattr(path, 'user.library-file-id').decode(),
                        version=int(os.getxattr(path, 'user.library-file-version').decode()))
        assert all(identity[k] == expected[name][k] for k in ('sha256', 'bytes')), name
        identities[name] = identity
    old_inventory = json.loads((ROOT / 'keiba_v48/reports/annual_2026/source_inventory.json').read_text())
    previous = {d['url']: d for d in old_inventory}
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        docs = [dict(r) for r in db.execute('select * from annual_report_documents where year=2026 order by url')]
        assert len(docs) == len(previous) == 234
        assert all(d['status'] == 'parsed' for d in docs)
        assert {d['url'] for d in docs} == set(previous)
        assert all(d['sha256'] == previous[d['url']]['sha256'] and
                   d['byte_count'] == previous[d['url']]['byte_count'] for d in docs)
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            names = [n for n in z.namelist() if n.startswith('pdf/')]
            assert len(names) == len(set(names)) == len(docs)
            manifest = json.loads(z.read('manifest.json'))
            assert {d['url']: d['sha256'] for d in manifest['documents']} == {d['url']: d['sha256'] for d in docs}
            for d in docs:
                raw = z.read('pdf/' + Path(d['local_path']).name)
                assert len(raw) == d['byte_count'] and hashlib.sha256(raw).hexdigest() == d['sha256']
        old_digest = raw_history_digest(db, 2026)
        with sqlite3.connect(baseline.resolve().as_uri() + '?mode=ro', uri=True) as old:
            assert old_digest == raw_history_digest(old, 2026)
        races = dict(db.execute('select substr(race_id,1,4),count(*) from annual_report_races group by 1'))
        runners = dict(db.execute('select substr(race_id,1,4),count(*) from annual_report_runners group by 1'))
        empty = db.execute('select count(*) from annual_report_races r where not exists '
                           '(select 1 from annual_report_runners n where n.race_id=r.race_id) '
                           'and substr(r.race_id,1,4)="2026"').fetchone()[0]
    now = dt.datetime.now(ZoneInfo('Asia/Tokyo'))
    audit = audit_database(database, 2, False, now.date().isoformat())
    assert audit['integrity'] == dict(sqlite='ok', foreign_key_violations=0)
    for key in ('runner_key_duplicate_groups', 'identity_link_disagreements', 'full_field_headcount_mismatches'):
        assert audit[key] == 0, key
    assert audit['database_unchanged'] and audit['unlinked_isolation']['cross_race_key_reuse'] == 0
    usable = audit['usable']
    assert sum(races.values()) == usable['races'] + usable['excluded_races'] + usable['void_races'] + empty
    assert races['2026'] == 2808 and runners['2026'] == 38608 and empty == 6
    report = dict(schema='keiba-annual-library-roundtrip-v1', verified=True, verified_at=now.isoformat(),
                  **identities, baseline=dict(sha256=digest(baseline), bytes=baseline.stat().st_size),
                  official_originals=234, original_hashes_match_previous=234, zip_crc='ok',
                  earlier_raw_history_unchanged=True, earlier_raw_history_sha256=old_digest,
                  race_counts_by_year=races, runner_counts_by_year=runners, empty_race_panels=empty,
                  usable=usable, integrity=audit['integrity'], latest_race_date=audit['race_date_range']['max'])
    inventory = [{k: d[k] for k in ('url', 'year', 'venue', 'meeting', 'day', 'sha256',
                                   'byte_count', 'fetched_at', 'parser_version')} for d in docs]
    return report, audit, inventory


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('db', 'archive', 'baseline', 'checkpoint', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    report, audit, docs = verify(args.db, args.archive, args.baseline, args.checkpoint)
    folder = Path(args.output)
    folder.mkdir(parents=True, exist_ok=True)
    for name, value in (('verification.json', report), ('data_audit.json', audit), ('source_inventory.json', docs)):
        (folder / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))
