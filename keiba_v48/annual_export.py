"""Export imported results and a machine-readable coverage/eligibility audit."""
import argparse
import collections
import csv
import json
from pathlib import Path
import sqlite3


FIELDS = ['race_id','race_date','off_timestamp','track','surface','distance_m','going',
          'horse_number','gate','finish_order','finish_position','horse_name','jockey_name',
          'horse_id','jockey_id','sex_age','carried_weight_raw','body_weight_raw',
          'body_weight_change_raw','finish_time_raw','final_win_odds','win_payout_100',
          'pre_off_odds','odds_timestamp','result_available_at','observed_at',
          'source_url','source_sha256','page_number','panel','extraction_status',
          'identity_status','model_history_eligible','issues_json']


def export(db_path, destination):
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    quality = collections.Counter()
    total = 0
    with (dest / 'annual_report_results.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        query = '''SELECT r.*, d.sha256,d.fetched_at, h.payload_json FROM annual_report_races r
            JOIN annual_report_documents d ON d.url=r.document_url
            JOIN annual_report_runners h ON h.race_id=r.race_id
            ORDER BY r.race_date,r.off_timestamp,r.race_id,h.finish_order'''
        for row in db.execute(query):
            runner = json.loads(row['payload_json'])
            meta = json.loads(row['metadata_json'])
            # The current race status is authoritative, even if a stale payload
            # retained a rank from an earlier successful parse.
            finish = runner.get('finish_position') if row['status'] == 'validated_result' else None
            values = {**dict(row), **runner, 'finish_position': finish,
                      'win_payout_100': meta.get('win_payout_100') if finish == 1 else None,
                      'observed_at': row['fetched_at'], 'source_url': row['document_url'],
                      'source_sha256': row['sha256'], 'extraction_status': row['status'],
                      'model_history_eligible': 'no'}
            writer.writerow({field: values.get(field) for field in FIELDS})
            total += 1
            quality[runner['identity_status']] += 1
    report = {
        'source': 'https://www.jra.go.jp/datafile/seiseki/',
        'document_counts': [dict(r) for r in db.execute('''SELECT year,count(*) AS indexed_pdfs,
            sum(local_path IS NOT NULL AND sha256 IS NOT NULL) AS downloaded_pdfs,
            sum(parser_version IS NOT NULL) AS processed_pdfs
            FROM annual_report_documents GROUP BY year ORDER BY year''')],
        'document_statuses': dict(db.execute('SELECT status,count(*) FROM annual_report_documents GROUP BY status').fetchall()),
        'race_statuses': dict(db.execute('SELECT status,count(*) FROM annual_report_races GROUP BY status').fetchall()),
        'runner_rows': total,
        'runner_identity_statuses': dict(quality),
        'official_id_linked_rows': db.execute('SELECT count(*) FROM annual_report_runners WHERE horse_id IS NOT NULL AND jockey_id IS NOT NULL').fetchone()[0],
        'model_history_eligible_rows': 0,
        'legacy_tables': {table: db.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in ('races','documents','runner_results') if db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()},
        'integrity_check': db.execute('PRAGMA integrity_check').fetchone()[0],
        'foreign_key_violations': len(db.execute('PRAGMA foreign_key_check').fetchall()),
        'review_reasons': [dict(r) for r in db.execute('''SELECT issues_json,count(*) AS races FROM annual_report_races
            WHERE status='requires_review' GROUP BY issues_json ORDER BY races DESC LIMIT 20''')],
        'document_errors': [dict(r) for r in db.execute('SELECT url,error FROM annual_report_documents WHERE error IS NOT NULL')],
        'limitations': [
            'validated_result means structural checks, not manual certification or verified official IDs',
            'outlined/reconstructed numbers, exceptional finishes and inconsistent fields remain quarantined',
            'finish_order is printed row order; finish_position is NULL for races requiring review',
            'final_win_odds are post-race labels, never substituted for pre-off odds',
            'observed_at is download time, not historical result publication time',
            'ID linkage and historical result publication times must be resolved before model history export',
        ]}
    (dest / 'annual_ingest_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    # A convenient SQL projection keeps labels distinct from historical predictors.
    # Refresh our projection on existing archives as well as new databases.
    db.execute('DROP VIEW IF EXISTS annual_result_labels')
    db.execute('''CREATE VIEW annual_result_labels AS
        SELECT r.race_id,r.race_date,r.track,r.surface,r.distance_m,r.going,
          h.horse_number,h.horse_name,h.jockey_name,
          CASE WHEN r.status='validated_result'
            THEN json_extract(h.payload_json,'$.finish_position') END AS finish_position,
          json_extract(h.payload_json,'$.final_win_odds') AS final_win_odds,
          r.status AS extraction_status,r.document_url AS source_url
        FROM annual_report_races r JOIN annual_report_runners h ON r.race_id=h.race_id''')
    db.commit()
    db.close()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.db, args.output), ensure_ascii=False, indent=2))
