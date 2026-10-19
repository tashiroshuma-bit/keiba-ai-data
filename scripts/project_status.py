"""Validate the shared project state without downloading or modifying data."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]


def canonical_digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def validate_state(state, root=ROOT):
    root = Path(root).resolve()
    errors = []

    def read(relative):
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError('reference escapes repository: ' + relative)
        return json.loads(path.read_text(encoding='utf-8'))

    try:
        if state['schema'] != 'keiba-project-state-v1':
            errors.append('unsupported project state schema')
        model = state['active_model']
        manifest = read(model['manifest'])
        if canonical_digest(read(model['path'])) != model['sha256']:
            errors.append('active model artifact hash differs from project state')
        if manifest['model_sha256'] != model['sha256']:
            errors.append('active manifest hash differs from project state')
        for key in ('status', 'strict_production_validated', 'live_bet_generation'):
            if manifest[key] != model[key]:
                errors.append('active manifest differs: ' + key)
        review_path = state['latest_research'].get('adoption_review', 'keiba_v48/reports/integration/adoption_review.json')
        review = read(review_path)
        linked_review = (root / model['manifest']).parent / manifest['last_review']['report']
        if linked_review.resolve() != (root / review_path).resolve():
            errors.append('active manifest last review is stale')
        if review['active_model_sha256'] != model['sha256']:
            errors.append('adoption review refers to a different active model')
        if review['forward_observed_races'] != state['forward']['observed_races']:
            errors.append('forward count differs from review')
        audit = read(state['latest_research']['data_audit'])
        for source, target in (('repaired_db_sha256', 'sha256'), ('repaired_db_bytes', 'bytes')):
            if audit[source] != state['database'][target]:
                errors.append('database identity differs from latest repair evidence: ' + target)
        if audit['usable_races_after'] != state['latest_research']['usable_races']:
            errors.append('usable race count differs from latest repair evidence')
        if audit['excluded_races_after'] != state['latest_research']['excluded_races']:
            errors.append('excluded race count differs from latest repair evidence')
        for name in state['latest_research']['comparison_files']:
            report = read(name)
            if report['input_db_sha256'] != state['database']['sha256']:
                errors.append('comparison uses a different database: ' + name)
            if report['exact_original_EV_cohort_structural_vs_original']['races'] != state['latest_research']['paired_cohort']:
                errors.append('comparison cohort differs: ' + name)
            for filename, expected in report['source_code_sha256'].items():
                actual = hashlib.sha256((root / 'keiba_v48' / filename).read_bytes()).hexdigest()
                if actual != expected:
                    errors.append('comparison source changed; reconcile research evidence: ' + filename)
    except (KeyError, ValueError, OSError) as exc:
        errors.append(str(exc))
    return errors


def verify_database(path, expected):
    path = Path(path).resolve()
    if path.stat().st_size != expected['bytes']:
        raise ValueError('database size differs; repository stub/old version is not canonical')
    with path.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    if digest != expected['sha256']:
        raise ValueError('database SHA256 differs from project state')
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        if db.execute('pragma integrity_check').fetchall() != [('ok',)]:
            raise ValueError('database integrity check failed')
        if db.execute('pragma foreign_key_check').fetchall():
            raise ValueError('database foreign key check failed')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', help='Optional materialized canonical DB; opened read-only')
    args = parser.parse_args()
    state = json.loads((ROOT / 'PROJECT_STATE.json').read_text())
    errors = validate_state(state)
    verified = False
    if args.db and not errors:
        try:
            verified = verify_database(args.db, state['database'])
        except (ValueError, OSError, sqlite3.Error) as exc:
            errors.append(str(exc))
    print(json.dumps(dict(valid=not errors, errors=errors,
                         database_version=state['database']['version'],
                         database_local_verified=verified,
                         usable_races=state['latest_research']['usable_races'],
                         live_bet_generation=state['active_model']['live_bet_generation']),
                     ensure_ascii=False))
    raise SystemExit(bool(errors))


if __name__ == '__main__':
    main()
