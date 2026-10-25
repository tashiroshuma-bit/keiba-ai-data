import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('observed_profile',ROOT/'scripts/forecast_rank_profile.py')
profile_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(profile_module)


class ObservedProfileTests(unittest.TestCase):
    def test_bound_profile_forecasts_full_field_and_discloses_missing_history(self):
        profile=json.loads((ROOT/'operations/prediction_policy/observed_history_rank.json').read_text())
        now=dt.datetime.now(dt.timezone.utc)
        rows=[dict(race_id='future',horse_number=str(i+1),horse_id=f'jra:{i+1}',jockey_id='jra:1',
            track='東京',surface='turf',distance_m=1600,sex_age='牡3',field_complete='yes',expected_runners=4,
            off_timestamp=(now+dt.timedelta(days=2)).isoformat(),features_asof=now.isoformat(),
            feature_generation_mode='observed_history',source_url='https://example.test/card',source_sha256='a'*64) for i in range(4)]
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'db';db.write_bytes(b'fixture');profile['database_sha256']=hashlib.sha256(b'fixture').hexdigest()
            with patch('rank_forecast.load_observed_enriched',return_value=[]):
                result=profile_module.create(db,rows,profile,7)
                self.assertEqual(len(result['runners']),4)
                self.assertEqual(result['prediction_basis']['runners_with_no_observed_history'],4)
                self.assertFalse(result['prediction_basis']['mean_imputed_career_proxy'])
                self.assertAlmostEqual(sum(r['p_first'] for r in result['runners']),1)
                self.assertEqual(result['allocation'],dict(bets=[],stake_yen=0))
            rows[0]['feature_generation_mode']='CAREER_TOTALS_PROXY'
            with self.assertRaises(ValueError):profile_module.create(db,rows,profile,7)
            rows[0]['feature_generation_mode']='observed_history';rows[0]['source_sha256']=''
            with self.assertRaises(ValueError):profile_module.create(db,rows,profile,7)
            profile['database_sha256']='0'*64
            with self.assertRaises(ValueError):profile_module.create(db,rows,profile,7)


if __name__=='__main__':unittest.main()
