"""Explain every race excluded from the win-model field without guessing."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sqlite3

from enriched_features import load_archive
from exceptional_results import competition_ranks_are_complete
from pdf_performance import parse_times


def audit(db_path, lag_days=2):
    _, fields, eligibility = load_archive(db_path, lag_days, allow_unlinked_fields=True)
    db = sqlite3.connect('file:' + str(Path(db_path).resolve()) + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    excluded = {row['race_id']: dict(row) for row in eligibility['excluded_races']}
    parser_rejections = collections.Counter()
    detailed = []
    for race_id, item in sorted(excluded.items()):
        race = db.execute('select * from annual_report_races where race_id=?', (race_id,)).fetchone()
        raw_rows = [json.loads(row[0]) for row in db.execute(
            'select payload_json from annual_report_runners where race_id=? order by finish_order', (race_id,))]
        metadata = json.loads(race['metadata_json'])
        if race['expected_runners'] is None:
            parser_reason = 'missing expected runner count'
        else:
            try:
                parse_times(raw_rows, race['expected_runners'], json.loads(race['issues_json']),
                            metadata.get('raw_text', ''), True)
                parser_reason = 'parsed_but_failed_field_eligibility'
            except ValueError as error:
                parser_reason = str(error)
        parser_rejections[parser_reason] += 1
        rich = db.execute('select status,payload_json from enriched_results where race_id=?', (race_id,)).fetchone()
        detailed.append(dict(
            race_id=race_id,
            eligibility_reasons=item['reasons'],
            pdf_performance_evidence=False,
            cached_result_page_status=rich['status'] if rich else 'missing',
            annual_parser_status=race['status'],
            annual_parser_issues=json.loads(race['issues_json']),
            performance_parser_rejection=parser_reason,
        ))
    recovered = []
    for row in db.execute("select race_id,payload_json from enriched_results where status='complete'"):
        rich = json.loads(row['payload_json'])
        active = set(rich['active_horse_numbers'])
        runners = [r for r in rich['runners'] if r['horse_number'] in active]
        ranks = [r.get('finish_position') for r in runners if r.get('finish_position') is not None]
        if len(ranks) != len(set(ranks)):
            if not competition_ranks_are_complete(runners):
                raise ValueError('complete source contains invalid dead-heat ranks: ' + row['race_id'])
            recovered.append(dict(
                race_id=row['race_id'],
                source_url=rich['source_url'],
                source_sha256=rich['source_sha256'],
                unique_winner=sum(r == 1 for r in ranks) == 1,
                tied_ranks=sorted(rank for rank, count in collections.Counter(ranks).items() if count > 1),
            ))
    result = dict(
        policy='win model admits only a unique winner and complete standard competition ranks',
        lag_days=lag_days,
        usable_races=len({row['race_id'] for row in fields}),
        excluded_races=len(detailed),
        recovered_nonwinning_dead_heats=len(recovered),
        exclusion_reason_memberships={k.split('reason:', 1)[1]: v for k, v in eligibility['exclusions'].items() if k.startswith('reason:')},
        performance_parser_rejections=dict(sorted(parser_rejections.items())),
        missing_cached_result_pages=sum(row['cached_result_page_status'] == 'missing' for row in detailed),
        recovered_dead_heats=recovered,
        excluded=detailed,
        integrity_check=db.execute('pragma integrity_check').fetchone()[0],
        foreign_key_violations=len(db.execute('pragma foreign_key_check').fetchall()),
    )
    db.close()
    raw = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    result['content_sha256_without_self'] = hashlib.sha256(raw).hexdigest()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--lag-days', type=int, default=2)
    args = parser.parse_args()
    report = audit(args.db, args.lag_days)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k not in ('recovered_dead_heats', 'excluded')}, ensure_ascii=False))
