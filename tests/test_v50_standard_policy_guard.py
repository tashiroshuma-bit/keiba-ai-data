"""Regression: the user-approved v50 route must not silently drift."""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.standard_v50_forecast import standard_forecast


class V50StandardPolicyGuardTests(unittest.TestCase):
    def test_rejects_state_route_drift_before_database_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            forecast = root / "forecast.json"
            state = root / "state.json"
            policy = root / "policy.json"
            output = root / "output.json"
            forecast.write_text("{}", encoding="utf-8")
            state.write_text(json.dumps({
                "database": {"version": 10, "sha256": "unused"},
                "standard_forecast": {
                    "version": "v49", "adopted_by_user": True,
                    "policy": "operations/prediction_policy/standard_v50.json",
                    "entrypoint": "scripts/standard_v50_forecast.py"
                }
            }), encoding="utf-8")
            policy.write_text(json.dumps({
                "standard_version": "v50", "standard_for_future_races": True,
                "live_bet_generation": False,
                "forecast_entrypoint": "scripts/standard_v50_forecast.py",
                "history_lag_days": 2, "overlay_weight": 1,
                "probability_temperature": 0.7
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "routing mismatch"):
                standard_forecast(forecast, root / "nonexistent.sqlite", output,
                                  state_path=state, policy_path=policy)
            self.assertFalse(output.exists())

    def test_rejects_temperature_drift_before_database_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            forecast, state, policy, output = (root / x for x in
                ("forecast.json", "state.json", "policy.json", "output.json"))
            forecast.write_text("{}", encoding="utf-8")
            state.write_text(json.dumps({
                "database": {"version": 10, "sha256": "unused"},
                "standard_forecast": {
                    "version": "v50", "adopted_by_user": True,
                    "policy": "operations/prediction_policy/standard_v50.json",
                    "entrypoint": "scripts/standard_v50_forecast.py"
                }
            }), encoding="utf-8")
            policy.write_text(json.dumps({
                "standard_version": "v50", "standard_for_future_races": True,
                "live_bet_generation": False,
                "forecast_entrypoint": "scripts/standard_v50_forecast.py",
                "history_lag_days": 2, "overlay_weight": 1,
                "probability_temperature": 1.25
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "approved parameters"):
                standard_forecast(forecast, root / "nonexistent.sqlite", output,
                                  state_path=state, policy_path=policy)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
