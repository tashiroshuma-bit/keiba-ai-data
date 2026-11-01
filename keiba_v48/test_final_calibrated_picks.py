"""Regression guard: final forecast picks must use calibrated p/q.

This checks the actual forecast function AST, not a synthetic race dataset.
"""
import ast
import pathlib
import unittest


class FinalCalibrationPickOrder(unittest.TestCase):
    def test_final_decisions_follow_optional_calibration(self):
        source = pathlib.Path(__file__).with_name("rank_forecast.py").read_text()
        tree = ast.parse(source)
        forecast = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "forecast")
        calibration = next(n for n in forecast.body if isinstance(n, ast.If) and isinstance(n.test, ast.Name) and n.test.id == "calibration_path")
        calls = []
        for node in forecast.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                name = node.value.func.id if isinstance(node.value.func, ast.Name) else None
                if name == "picks":
                    calls.append(node.lineno)
        self.assertTrue(calls, "forecast must compute picks")
        self.assertGreater(max(calls), calibration.end_lineno,
                           "final picks must be recomputed after calibration")

    def test_probability_method_discloses_assumptions(self):
        source = pathlib.Path(__file__).with_name("rank_forecast.py").read_text()
        tree = ast.parse(source)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "forecast")
        method = next(n for n in fn.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "probability_method" for t in n.targets))
        keys = {k.arg for k in method.value.keywords} if isinstance(method.value, ast.Call) else set()
        required = {"model_sha256", "selection_sha256", "top3_formula",
                    "ordered_top3_formula", "unordered_top3_formula",
                    "current_odds_used_as_model_feature", "final_calibration"}
        self.assertTrue(required.issubset(keys))
        self.assertIn("probability_method=probability_method", source)

    def test_exact_set_follows_final_picks(self):
        source = pathlib.Path(__file__).with_name("rank_forecast.py").read_text()
        forecast = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "forecast")
        body = source.splitlines()
        final_picks = max(i for i, line in enumerate(body, 1) if "winner, trio, ordered = picks(p, q, numbers)" in line)
        exact_set_lines = [i for i, line in enumerate(body, 1) if "trio, _ = exact_set(q, numbers)" in line]
        self.assertTrue(any(i > final_picks for i in exact_set_lines),
                        "exact_set decision must use final calibrated joint probabilities")


if __name__ == "__main__":
    unittest.main()
