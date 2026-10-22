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
        research_db = state['latest_research'].get('database', state['database'])
        for source, target in (('repaired_db_sha256', 'sha256'), ('repaired_db_bytes', 'bytes')):
            if audit[source] != research_db[target]:
                errors.append('database identity differs from latest repair evidence: ' + target)
        if audit['usable_races_after'] != state['latest_research']['usable_races']:
            errors.append('usable race count differs from latest repair evidence')
        if audit['excluded_races_after'] != state['latest_research']['excluded_races']:
            errors.append('excluded race count differs from latest repair evidence')
        for name in state['latest_research']['comparison_files']:
            report = read(name)
            if report['input_db_sha256'] != research_db['sha256']:
                errors.append('comparison uses a different database: ' + name)
            if report['exact_original_EV_cohort_structural_vs_original']['races'] != state['latest_research']['paired_cohort']:
                errors.append('comparison cohort differs: ' + name)
            for filename, expected in report['source_code_sha256'].items():
                actual = hashlib.sha256((root / 'keiba_v48' / filename).read_bytes()).hexdigest()
                if actual != expected:
                    archived = state.get('historical_source_snapshots', {}).get(filename)
                    snapshot = (root / archived['path']).resolve() if archived else None
                    if not (archived and archived['sha256'] == expected and snapshot.is_relative_to(root)
                            and hashlib.sha256(snapshot.read_bytes()).hexdigest() == expected):
                        errors.append('comparison source changed; reconcile research evidence: ' + filename)
        roi = state['latest_research'].get('roi95_experiment')
        if roi:
            summary = read(roi['summary'])
            inventory = read(roi['inventory'])
            folder = (root / roi['inventory']).parent
            for name, evidence in inventory.items():
                artifact = (folder / name).resolve()
                if not artifact.is_relative_to(folder.resolve()):
                    raise ValueError('ROI95 reference escapes evidence directory')
                if artifact.stat().st_size != evidence['bytes'] or hashlib.sha256(artifact.read_bytes()).hexdigest() != evidence['sha256']:
                    errors.append('ROI95 artifact identity differs: ' + name)
            for lag in (2, 7):
                report = read(str((folder / f'evaluation_lag{lag}.json').relative_to(root)))
                verification = read(str((folder / f'verification_lag{lag}.json').relative_to(root)))
                actual = summary[str(lag)]['full_3314_candidate_same_policy']
                if (actual['return_pct'] != roi['return_pct'][f'lag{lag}'] or
                    actual['bet_races'] != roi['selected_bets'][f'lag{lag}'] or
                    report['selected_policy']['exploratory_metrics'] != actual or
                    not verification['verified'] or
                    verification['independently_recomputed_return_pct'] != actual['return_pct']):
                    errors.append('ROI95 metrics differ from verified research evidence')
                if report['input_db_sha256'] != research_db['sha256']:
                    errors.append('ROI95 uses a different database')
            if roi['live_eligible'] is not False or review['live_model_promotion_approved'] is not False:
                errors.append('ROI95 retrospective model cannot be live eligible')
        current = state.get('latest_data_work', {})
        if (research_db['sha256'] != state['database']['sha256'] and
                current.get('status') != 'saved_and_roundtrip_verified'):
            errors.append('current database changed without verified saved readback')
        if current.get('status') == 'saved_and_roundtrip_verified':
            saved = read(current['verification'])
            quality = read(current['data_audit'])
            if saved['verified'] is not True or saved['earlier_raw_history_unchanged'] is not True:
                errors.append('current database roundtrip is not verified')
            for key in ('sha256', 'bytes', 'library_file_id', 'version'):
                if saved['database'][key] != state['database'][key]:
                    errors.append('current database differs from saved readback: ' + key)
            if (quality['input_db_sha256'] != state['database']['sha256'] or
                    quality['input_db_bytes'] != state['database']['bytes'] or
                    saved['usable'] != quality['usable'] or
                    saved['latest_race_date'] != current['latest_race_date']):
                errors.append('current database audit differs from saved readback')
            if (quality['integrity'] != {'sqlite': 'ok', 'foreign_key_violations': 0} or
                    quality['runner_key_duplicate_groups'] != 0 or
                    quality['identity_link_disagreements'] != 0 or
                    quality['full_field_headcount_mismatches'] != 0 or
                    saved['usable']['races'] != current['usable_races']):
                errors.append('current database quality gate failed')
            for key in ('sha256', 'bytes', 'library_file_id', 'version'):
                if saved['originals'][key] != state['sources']['annual_2026'][key]:
                    errors.append('current originals differ from saved readback: ' + key)
            for key in ('sha256', 'bytes'):
                if saved['baseline'][key] != research_db[key]:
                    errors.append('historical research database differs from preserved baseline: ' + key)
        rank = state.get('latest_rank_research')
        if rank:
            if state['development_objective']['primary'] != 'rank_prediction_accuracy':
                errors.append('rank development objective differs')
            registry = read(rank['predictions_registry'])
            for name in rank['evaluation_files']:
                report = read(name)
                folder = (root / name).parent
                lag = '2' if name.endswith('lag2.json') else '7'
                selection = read(str((folder / f'selection_lag{lag}.json').relative_to(root)))
                verification = read(str((folder / f'verification_lag{lag}.json').relative_to(root)))
                artifact = (folder / f'model_lag{lag}.json')
                if (hashlib.sha256(artifact.read_bytes()).hexdigest() != report['model_sha256'] or
                        report['model_sha256'] != selection['model_sha256'] or
                        report['predictions_sha256'] != registry[lag]['sha256'] or
                        report['predictions_sha256'] != verification['predictions_sha256'] or
                        report['input_db_sha256'] != rank['database']['sha256'] or
                        report['baseline_model_sha256'] != rank['baseline_model_sha256']):
                    errors.append('rank artifact identity differs')
                if (report['years'] != rank['metrics']['lag'+lag] or verification['verified'] is not True or
                        verification['races'] != sum(v['candidate']['races'] for v in report['years'].values()) or
                        registry[lag]['races'] != verification['races'] or
                        report['maximum_reload_error'] != 0 or report['database_unchanged'] is not True or
                        report['live_model_promoted'] is not False):
                    errors.append('rank verified metrics differ')
                if hashlib.sha256((folder / f'selection_lag{lag}.json').read_bytes()).hexdigest() != report['selection_sha256']:
                    errors.append('rank selection was changed after evaluation')
                for source, expected in selection['source_sha256'].items():
                    if hashlib.sha256((root / 'keiba_v48' / source).read_bytes()).hexdigest() != expected:
                        errors.append('rank source changed; reconcile evidence: '+source)
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
                         usable_races=(state.get('latest_data_work', {}).get('usable_races')
                                       or state['latest_research']['usable_races']),
                         live_bet_generation=state['active_model']['live_bet_generation']),
                     ensure_ascii=False))
    raise SystemExit(bool(errors))


if __name__ == '__main__':
    main()
