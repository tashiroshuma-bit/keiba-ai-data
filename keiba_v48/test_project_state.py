"""Regression gates for cross-thread state and canonical database selection."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('shared_project_status', ROOT / 'scripts/project_status.py')
project = importlib.util.module_from_spec(spec)
spec.loader.exec_module(project)


class SharedProjectStateTest(unittest.TestCase):
    def setUp(self):
        self.state = json.loads((ROOT / 'PROJECT_STATE.json').read_text())

    def test_actual_evidence_and_active_model_match(self):
        self.assertEqual(project.validate_state(self.state), [])

    def test_old_database_state_is_rejected(self):
        stale = copy.deepcopy(self.state)
        stale['database']['sha256'] = 'fbe6f00be236c319bcd9ff9cd60cd6ed3d28e0c75f2edf984201b4668fd57ce4'
        self.assertTrue(any('database' in error for error in project.validate_state(stale)))

    def test_unreviewed_model_and_unsafe_reference_are_rejected(self):
        changed = copy.deepcopy(self.state)
        changed['active_model']['sha256'] = '0' * 64
        self.assertTrue(any('active' in error for error in project.validate_state(changed)))
        changed['active_model']['path'] = '../outside-model.json'
        self.assertTrue(any('escapes repository' in error for error in project.validate_state(changed)))

    def test_repository_database_stub_is_not_accepted(self):
        with self.assertRaisesRegex(ValueError, 'size differs'):
            project.verify_database(ROOT / 'jra_2023_2025.sqlite', self.state['database'])

    def test_roi95_claim_must_match_verified_artifacts(self):
        stale = copy.deepcopy(self.state)
        stale['latest_research']['roi95_experiment']['return_pct']['lag2'] = 150
        self.assertTrue(any('ROI95 metrics' in error for error in project.validate_state(stale)))

    def test_historical_source_snapshot_requires_exact_hash(self):
        stale = copy.deepcopy(self.state)
        stale['historical_source_snapshots']['annual_parser.py']['sha256'] = '0' * 64
        self.assertTrue(any('comparison source changed' in error for error in project.validate_state(stale)))

    def test_current_database_requires_completed_roundtrip(self):
        stale = copy.deepcopy(self.state)
        stale['latest_data_work']['status'] = 'locally_verified_candidate_persistent_save_blocked'
        self.assertTrue(any('without verified saved readback' in e for e in project.validate_state(stale)))

    def test_research_keeps_its_actual_database(self):
        stale = copy.deepcopy(self.state)
        stale['latest_research']['database'] = copy.deepcopy(stale['database'])
        self.assertTrue(any('different database' in e or 'database identity' in e for e in project.validate_state(stale)))

    def test_saved_originals_identity_is_checked(self):
        stale = copy.deepcopy(self.state)
        stale['sources']['annual_2026']['sha256'] = '0' * 64
        self.assertTrue(any('originals differ' in e for e in project.validate_state(stale)))

    def test_rank_claims_must_match_saved_evaluation(self):
        stale = copy.deepcopy(self.state)
        stale['latest_rank_research']['metrics']['lag2']['2025']['candidate']['winner_hit'] = .8
        self.assertTrue(any('rank verified metrics' in e for e in project.validate_state(stale)))

    def test_rank_input_database_is_pinned(self):
        stale = copy.deepcopy(self.state)
        stale['latest_rank_research']['database']['sha256'] = '0'*64
        self.assertTrue(any('rank artifact identity' in e for e in project.validate_state(stale)))

    def test_unmet_exact_targets_cannot_be_reported_as_met(self):
        stale = copy.deepcopy(self.state)
        stale['latest_exact_rank_research']['all_targets_met'] = True
        self.assertTrue(any('target attainment' in e for e in project.validate_state(stale)))

    def test_user_exact_goals_are_pinned(self):
        stale = copy.deepcopy(self.state)
        stale['development_objective']['targets']['winner_hit'] = .2
        self.assertTrue(any('targets differ' in e for e in project.validate_state(stale)))

    def test_relative_challenger_cannot_be_silently_adopted(self):
        stale=copy.deepcopy(self.state)
        stale['latest_relative_rank_research']['adopted']=True
        self.assertTrue(any('not approved for adoption' in e for e in project.validate_state(stale)))
        stale=copy.deepcopy(self.state)
        stale['latest_relative_rank_research']['selected']['lag2']='another_model'
        self.assertTrue(any('relative rank evidence' in e for e in project.validate_state(stale)))

    def test_history_metrics_and_goal_claims_match_saved_replay(self):
        stale=copy.deepcopy(self.state)
        stale['latest_history_research']['metrics']['lag7']['2026']['candidate']['winner_hit']=.8
        self.assertTrue(any('history rank evidence' in e for e in project.validate_state(stale)))
        stale=copy.deepcopy(self.state);stale['latest_history_research']['all_targets_met']=True
        self.assertTrue(any('history target attainment' in e for e in project.validate_state(stale)))

    def test_empty_preoff_page_cannot_count_as_complete_field(self):
        stale=copy.deepcopy(self.state);stale['preoff_information']['complete_future_fields']=1
        self.assertTrue(any('preoff observation' in e for e in project.validate_state(stale)))


if __name__ == '__main__':
    unittest.main()
