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
                current.get('status') not in ('saved_and_roundtrip_verified','identity_repaired_saved_and_roundtrip_verified')):
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
        if current.get('status') == 'identity_repaired_saved_and_roundtrip_verified':
            saved=read(current['verification']);quality=read(current['data_audit']);repair=read(current['recovery'])
            previous_saved=read(state['previous_data_work']['verification'])
            if previous_saved['database']['sha256'] != saved['input_database_sha256']:
                errors.append('identity recovery input differs from previous saved database')
            for key in ('sha256','bytes','library_file_id','version'):
                if previous_saved['originals'][key] != state['sources']['annual_2026'][key]:
                    errors.append('current originals differ from previous saved readback: '+key)
            if (saved.get('verified') is not True or saved.get('saved_readback') is not True or
                    saved.get('outcomes_and_nonidentity_payload_unchanged') is not True or
                    saved.get('names_corrected_with_original_text_preserved') != len(repair['text_repairs']) or
                    saved.get('newly_linked_rows') != repair['newly_linked_rows'] or
                    saved['input_database_sha256'] != repair['input_sha256']):
                errors.append('identity repair readback or preservation evidence differs')
            if state['database']['version'] == saved['database']['version']:
                for key in ('sha256','bytes','library_file_id','version'):
                    if saved['database'][key] != state['database'][key]:
                        errors.append('identity database differs from saved readback: '+key)
            elif state['database']['version'] in (11,12) and saved['database']['version'] == 10:
                # Keep v10 -> v11 official podium evidence independently checked.
                supplement=read('operations/data_updates/canonical_db_v11_update_verified.json')
                expected_v11 = state['database'] if state['database']['version'] == 11 else {
                    'sha256':state['database']['previous_sha256'],
                    'bytes':supplement['bytes'],
                    'library_file_id':state['database']['previous_library_file_id'],
                    'version':11
                }
                for key in ('sha256','bytes','library_file_id','version'):
                    if supplement[key] != expected_v11[key]:
                        errors.append('v11 supplement database differs from saved readback: '+key)
                if (supplement['prior_sha256'] != saved['database']['sha256'] or
                    supplement['prior_bytes'] != saved['database']['bytes'] or
                    supplement['prior_version'] != saved['database']['version'] or
                    supplement['readback_verified'] is not True or
                    supplement['integrity_check'] != 'ok' or
                    supplement['foreign_key_check'] != 'ok' or
                    supplement['canonical_historical_races_unchanged'] != 13176 or
                    supplement['canonical_historical_runner_rows_unchanged'] != 181345 or
                    supplement['official_supplement_races'] != 36 or
                    supplement['official_supplement_placing_rows'] != 108 or
                    supplement['supplementary_podium_records_train_eligible'] is not False):
                    errors.append('v11 supplement has unverified preservation or provenance')
                if state['database']['version'] == 12:
                    v12=read('operations/data_updates/canonical_db_v12_update_verified.json')
                    for key in ('sha256','bytes','library_file_id','version'):
                        if v12[key] != state['database'][key]:
                            errors.append('v12 official horse ID readback mismatch: '+key)
                    if (v12['prior_sha256'] != supplement['sha256'] or
                        v12['prior_bytes'] != supplement['bytes'] or
                        v12['prior_library_file_id'] != supplement['library_file_id'] or
                        v12['prior_version'] != supplement['version'] or
                        v12.get('readback_verified') is not True or
                        v12.get('readback_sha256') != v12['sha256'] or
                        v12.get('readback_bytes') != v12['bytes'] or
                        v12.get('integrity_check') != 'ok' or
                        v12.get('foreign_key_check') != 'ok' or
                        v12.get('canonical_historical_races_unchanged') != 13176 or
                        v12.get('canonical_historical_runner_rows_unchanged') != 181345 or
                        v12.get('validated_result_races') != 11201 or
                        v12.get('validated_result_runner_rows') != 154191 or
                        v12.get('validated_null_before') != 66360 or
                        v12.get('validated_ids_newly_verified') != 66360 or
                        v12.get('validated_null_after') != 0 or
                        v12.get('requires_review_null_after') != 10957 or
                        v12.get('official_race_html_exact') != 66346 or
                        v12.get('pdf_cid_extraction_repairs') != 13 or
                        v12.get('foreign_horse_crosschecked') != 1 or
                        v12.get('identity_link_disagreements') != 0 or
                        v12.get('payload_json_identity_disagreements') != 0 or
                        v12.get('existing_horse_id_conflicts') != 0 or
                        v12.get('old_canonical_v11_unchanged') is not True or
                        v12.get('source_primary_jra_originals_archived') != 47 or
                        v12.get('source_original_archive_readback_verified') is not True or
                        v12.get('standard_v50_forecast_unchanged') is not True or
                        v12.get('v51_production_promoted') is not False):
                        errors.append('v12 horse-ID full recovery missing independent persistence/provenance proof')
                    if (state['database'].get('library_readback_sha256_verified') is not True or
                        state.get('horse_id_full_recovery_20261111',{}).get('remaining_validated') != 0 or
                        state.get('horse_id_full_recovery_20261111',{}).get('remaining_requires_review') != 10957):
                        errors.append('v12 active state does not match validated horse-ID recovery scope')
            else:
                errors.append('canonical DB version lacks verified historical-to-current readback chain')
            if (quality['input_db_sha256'] != saved['database']['sha256'] or
                    repair['output_sha256'] != saved['database']['sha256'] or
                    quality['input_db_bytes'] != saved['database']['bytes'] or
                    quality['integrity'] != {'sqlite':'ok','foreign_key_violations':0} or
                    quality['identity_link_disagreements'] != 0 or
                    quality['runner_key_duplicate_groups'] != 0 or
                    quality['full_field_headcount_mismatches'] != 0 or
                    saved['usable'] != quality['usable'] or saved['usable']['races'] != current['usable_races'] or
                    saved['observed_identity_errors'] or saved['latest_race_date'] != current['latest_race_date']):
                errors.append('identity repair database quality gate failed')
        probability=state.get('latest_probability_research')
        if probability:
            registry=read(probability['predictions_registry'])
            folder=(root/probability['predictions_registry']).parent
            for lag in ('2','7'):
                report=read(str((folder/f'confidence_evaluation_lag{lag}.json').relative_to(root)))
                rule_path=folder/f'confidence_lag{lag}.json'
                rule=read(str(rule_path.relative_to(root)))
                verified=read(str((folder/f'verification_lag{lag}.json').relative_to(root)))
                global_rule=read(str((folder/f'calibration_lag{lag}.json').relative_to(root)))
                if (hashlib.sha256(rule_path.read_bytes()).hexdigest() != report['calibration_sha256'] or
                        verified['calibration_sha256'] != report['calibration_sha256'] or
                        verified['predictions_sha256'] != report['predictions_sha256'] or
                        registry['confidence_predictions'][lag]['sha256'] != report['predictions_sha256'] or
                        registry['fit_evidence'][lag]['sha256'] != rule['fit_evidence_sha256'] or
                        report['years'] != probability['metrics']['lag'+lag] or
                        report['input_db_sha256'] != probability['database']['sha256'] or
                        report['rank_decisions_changed'] != 0 or report['active_model_promoted'] is not False or
                        verified['verified'] is not True or verified['races'] != 6036 or
                        verified['maximum_probability_replay_error'] != 0):
                    errors.append('probability correction evidence differs')
                selection_path=root/f'keiba_v48/reports/exact_rank/selection_lag{lag}.json'
                model_path=root/f'keiba_v48/reports/exact_rank/model_lag{lag}.json'
                if (rule['model_sha256'] != hashlib.sha256(model_path.read_bytes()).hexdigest() or
                        rule['base_selection_sha256'] != hashlib.sha256(selection_path.read_bytes()).hexdigest() or
                        rule['global_calibration_sha256'] != hashlib.sha256((folder/f'calibration_lag{lag}.json').read_bytes()).hexdigest()):
                    errors.append('probability correction base model differs')
                for artifact in (rule,global_rule):
                    for name,expected in artifact['source_sha256'].items():
                        if hashlib.sha256((root/'keiba_v48'/name).read_bytes()).hexdigest()!=expected:
                            errors.append('probability correction source differs: '+name)
        history = state.get('latest_history_research')
        if history:
            registry=read(history['predictions_registry']);folder=(root/history['predictions_registry']).parent
            for lag in ('2','7'):
                selection=read(str((folder/f'selection_lag{lag}.json').relative_to(root)))
                report=read(str((folder/f'evaluation_lag{lag}.json').relative_to(root)))
                verification=read(str((folder/f'verification_lag{lag}.json').relative_to(root)))
                for prefix,key in (('model','model_sha256'),('selection','selection_sha256')):
                    if hashlib.sha256((folder/f'{prefix}_lag{lag}.json').read_bytes()).hexdigest()!=report[key]:
                        errors.append('history rank artifact differs: '+prefix)
                if (report['predictions_sha256'] != registry[lag]['sha256'] or
                        report['predictions_sha256'] != verification['predictions_sha256'] or
                        report['model_sha256'] != verification['model_sha256'] or
                        selection['model_sha256'] != report['model_sha256'] or
                        verification['verified'] is not True or verification['races'] != 6036 or registry[lag]['races'] != verification['races'] or
                        verification['largest_independent_probability_error'] >= 1e-11 or
                        report['input_db_sha256'] != history['database']['sha256'] or
                        report['years'] != history['metrics']['lag'+lag] or
                        report['maximum_reload_error'] != 0 or report['database_unchanged'] is not True or
                        report['active_model_promoted'] is not False or history['active_model_replaced'] is not False):
                    errors.append('history rank evidence differs')
                targets=state['development_objective']['targets']
                if report['all_targets_met'] != all(v['candidate'][k]>=t for v in report['years'].values() for k,t in targets.items()):
                    errors.append('history target attainment differs')
                baseline=selection['grid'][0]['metrics'];options=[]
                for candidate in selection['grid']:
                    m=candidate['metrics']
                    if all(round(m[k]*m['races'])>=round(baseline[k]*baseline['races']) for k in targets):options.append(candidate)
                def score(candidate):
                    m=candidate['metrics'];product=1
                    for k,t in targets.items():product*=m[k]/t
                    return (-product,m['joint_log_loss'],candidate['name'])
                if (min(options,key=score)['name'] != selection['selected'] or report['selected'] != selection['selected'] or
                        history['selected']['lag'+lag] != selection['selected']):
                    errors.append('history candidate violates frozen selection')
                for name,digest in selection['source_sha256'].items():
                    if hashlib.sha256((root/'keiba_v48'/name).read_bytes()).hexdigest()!=digest:
                        errors.append('history source differs: '+name)
            attained=all(v['candidate'][k]>=t for annual in history['metrics'].values() for v in annual.values() for k,t in targets.items())
            if history['all_targets_met'] != attained:errors.append('history target attainment differs from shared state')
        preoff=state.get('preoff_information')
        if preoff:
            observed=read(preoff['observation'])
            raw_path=(root/preoff['observation'].replace('_observation.json','.html')).resolve()
            if (not raw_path.is_relative_to(root) or hashlib.sha256(raw_path.read_bytes()).hexdigest()!=observed['sha256'] or
                    (observed['full_field_attested'] is False and preoff['complete_future_fields']!=0) or
                    preoff['forecast_created'] != observed['forecast_created']):
                errors.append('preoff observation provenance or coverage differs')
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
        exact = state.get('latest_exact_rank_research')
        if exact:
            protocol = read(exact['protocol'])
            targets = protocol['targets']
            if targets != state['development_objective']['targets']:
                errors.append('exact rank targets differ from user goal protocol')
            registry = read(exact['predictions_registry'])
            all_met = True
            for lag in ('2', '7'):
                folder = 'keiba_v48/reports/exact_rank/'
                report = read(folder + f'evaluation_lag{lag}.json')
                selection = read(folder + f'selection_lag{lag}.json')
                checked = read(folder + f'verification_lag{lag}.json')
                if (report['input_db_sha256'] != exact['database']['sha256'] or
                        report['model_sha256'] != hashlib.sha256((root / folder / f'model_lag{lag}.json').read_bytes()).hexdigest() or
                        report['model_sha256'] != selection['model_sha256'] or
                        report['predictions_sha256'] != registry[lag]['sha256'] or
                        report['predictions_sha256'] != checked['predictions_sha256'] or checked['verified'] is not True or
                        selection['selected'] != report['selected'] or
                        report['selected'] != exact['selected']['lag'+lag] or
                        report['prediction_set_policy'] != exact['shadow_set_policy']['lag'+lag]):
                    errors.append('exact rank saved evidence differs')
                if (hashlib.sha256((root / folder / f'selection_lag{lag}.json').read_bytes()).hexdigest() != report['selection_sha256'] or
                        report['maximum_reload_error'] != 0 or not report['database_unchanged'] or
                        report['live_model_promoted'] is not False):
                    errors.append('exact rank freeze or reload verification differs')
                for name, expected in selection['source_sha256'].items():
                    if hashlib.sha256((root/'keiba_v48'/name).read_bytes()).hexdigest() != expected:
                        errors.append('exact rank source changed: '+name)
                for year, values in report['years'].items():
                    metrics = {k: values['candidate'][k] for k in targets}
                    met = all(metrics[k] >= targets[k] for k in targets)
                    all_met = all_met and met
                    if (metrics != exact['metrics']['lag'+lag][year] or
                            values['candidate']['all_targets_met'] != met or values['full_coverage'] is not True or
                            values['coverage_races'] != values['candidate']['races']):
                        errors.append('exact rank hit claims differ from all-race evidence')
                if checked['races'] != sum(v['candidate']['races'] for v in report['years'].values()):
                    errors.append('exact rank race coverage differs')
            if exact['all_targets_met'] != all_met:
                errors.append('exact rank target attainment is unsupported')
        for research_kind,state_key in (('relative','latest_relative_rank_research'),('evidence','latest_evidence_rank_research')):
            relative=state.get(state_key)
            if not relative:
                continue
            if relative['adopted'] or relative['active_model_replaced'] or relative['forward_observed_races']!=0:
                errors.append(research_kind+' rank challenger was not approved for adoption')
            attained=True
            winner_improved=True
            for lag in ('2','7'):
                prefix=f'keiba_v48/reports/{research_kind}_rank'
                folder=root/prefix
                report=read(prefix+f'/evaluation_lag{lag}.json')
                selection=read(prefix+f'/selection_lag{lag}.json')
                verification=read(prefix+f'/verification_lag{lag}.json')
                inventory=read(prefix+f'/prediction_inventory_lag{lag}.json')
                if (sha256_file(folder/f'model_lag{lag}.json')!=selection['model_sha256'] or
                    sha256_file(folder/f'selection_lag{lag}.json')!=report['selection_sha256'] or
                    report['model_sha256']!=selection['model_sha256'] or
                    report['input_db_sha256']!=relative['database']['sha256'] or
                    report['selected']!=selection['selected'] or
                    relative['selected']['lag'+lag]!=selection['selected'] or
                    verification['status']!='PASS' or report['maximum_reload_error']!=0 or
                    not report['database_unchanged'] or report['production_model_changed']):
                    errors.append(research_kind+' rank evidence differs')
                for name,item in inventory.items():
                    path=(folder/name).resolve()
                    if not path.is_relative_to(folder.resolve()) or sha256_file(path)!=item['sha256'] or path.stat().st_size!=item['bytes']:
                        errors.append(research_kind+' rank prediction inventory differs')
                count=sum(item['races'] for item in inventory.values())
                if count!=verification['races'] or count!=sum(v['races'] for v in report['years'].values()):
                    errors.append(research_kind+' rank coverage differs')
                for name,digest in selection['source_sha256'].items():
                    if sha256_file(root/'keiba_v48'/name)!=digest:errors.append(research_kind+' rank source differs: '+name)
                for v in report['years'].values():
                    attained=attained and all(v['candidate'][k]>=t for k,t in state['development_objective']['targets'].items())
                    winner_improved=winner_improved and v['candidate']['winner_hit']>v['baseline']['winner_hit']
            if relative['all_targets_met']!=attained:errors.append(research_kind+' rank target attainment unsupported')
            if research_kind=='evidence' and relative['winner_hit_improved_in_all_four_retrospective_comparisons']!=winner_improved:
                errors.append('evidence rank winner improvement claim differs')
            profile=read(relative['observed_history_profile'])
            if profile['career_total_proxy_allowed'] or profile['relative_challenger_adopted'] or profile['live_eligible']:
                errors.append('observed-history profile adoption differs')
            for artifacts in profile['lags'].values():
                for kind,item in artifacts.items():
                    if item is None:
                        if kind!='calibration':errors.append('observed-history profile artifact missing')
                        continue
                    path=(root/item['path']).resolve()
                    if not path.is_relative_to(root) or sha256_file(path)!=item['sha256']:
                        errors.append('observed-history profile artifact differs')
        actor=state.get('latest_actor_indices')
        if actor:
            snapshot=read(actor['snapshot']);checked=read(actor['verification'])
            folder=(root/actor['snapshot']).parent.resolve()
            if (snapshot['input_db_sha256']!=actor['database_sha256'] or snapshot['counts']!=actor['counts'] or
                checked['status']!='PASS' or checked['counts']!=snapshot['counts'] or
                checked['snapshot_sha256']!=sha256_file(root/actor['snapshot']) or
                actor['adjusted_races']!=snapshot['audit']['adjusted_fields'] or
                not snapshot['database_unchanged'] or not snapshot['audit']['solver_within_1e_4']):
                errors.append('horse/jockey index evidence differs')
            if (actor['new_probability_features_activated'] or actor['probability_improvement_claimed'] or
                actor['active_model_replaced'] or actor['formal_forward_added']!=0 or
                not actor['historical_use_requires_per_race_rebuild']):
                errors.append('horse/jockey indices have not been prediction-validated')
            if sha256_file(root/actor['protocol'])!=snapshot['protocol_sha256']:
                errors.append('horse/jockey index protocol differs')
            for name,digest in snapshot['code_sha256'].items():
                if sha256_file(root/'keiba_v48'/name)!=digest:errors.append('horse/jockey index source differs')
            for name,item in snapshot['inventory'].items():
                path=(folder/name).resolve()
                if not path.is_relative_to(folder) or sha256_file(path)!=item['sha256'] or path.stat().st_size!=item['bytes']:
                    errors.append('horse/jockey index catalogue differs')
        actor_hits=state.get('latest_actor_hit_research')
        if actor_hits:
            if (actor_hits['adopted'] or actor_hits['production_model_changed'] or actor_hits['formal_forward_added'] or
                actor_hits['new_classifier_trained'] or actor_hits['present_day_catalogue_used_for_past']):
                errors.append('actor hit benchmark role differs')
            for lag in ('2','7'):
                folder=root/'keiba_v48/reports/actor_hit'
                report=read(f'keiba_v48/reports/actor_hit/evaluation_lag{lag}.json')
                checked=read(f'keiba_v48/reports/actor_hit/verification_lag{lag}.json')
                if (report['input_db_sha256']!=actor_hits['database_sha256'] or checked['status']!='PASS' or
                    checked['evaluation_sha256']!=sha256_file(folder/f'evaluation_lag{lag}.json') or
                    checked['races']!=actor_hits['races_per_lag'] or not checked['temporal_checks_all_pass'] or
                    not report['database_unchanged'] or report['production_model_changed'] or
                    not report['no_post_evaluation_rule_selection'] or report['new_classifier_trained']):
                    errors.append('actor hit benchmark evidence differs')
                if sha256_file(folder/f'index_snapshots_lag{lag}.json')!=report['index_snapshot_sha256']:
                    errors.append('actor hit temporal prefix evidence differs')
                for name,item in report['predictions_inventory'].items():
                    path=(folder/name).resolve()
                    if not path.is_relative_to(folder) or sha256_file(path)!=item['sha256'] or path.stat().st_size!=item['bytes']:
                        errors.append('actor hit prediction archive differs')
                if sum(item['races'] for item in report['predictions_inventory'].values())!=actor_hits['races_per_lag']:
                    errors.append('actor hit full coverage differs')
                for name,digest in report['source_sha256'].items():
                    if sha256_file(root/'keiba_v48'/name)!=digest:errors.append('actor hit source differs')
    except (KeyError, ValueError, OSError) as exc:
        errors.append(str(exc))
    return errors


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
