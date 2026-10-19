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


if __name__ == '__main__':
    unittest.main()
