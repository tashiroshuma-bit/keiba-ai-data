import unittest
from jockey_feature_overlay import overlay, rider_updates


class RiderOverlayTest(unittest.TestCase):
    def test_only_rider_columns_change_and_no_mutation(self):
        original = [{'values': [17, .2, 1], 'group': '東京/turf'}]
        result = overlay(original, [{'jockey_id': 'jra:005339'}],
                         ['ability', 'jockey_form', 'jockey_identity_missing'],
                         {'jra:005339': {'value': .58, 'samples': 100}})
        self.assertEqual(result[0]['values'], [17, .58, 0])
        self.assertEqual(original[0]['values'], [17, .2, 1])

    def test_missing_history_and_identity_are_explicit(self):
        self.assertEqual(rider_updates('jra:005678', {})[1], 0)
        self.assertEqual(rider_updates(None, {})[0]['jockey_identity_missing'], 1)

    def test_invalid_samples_and_namespace_rejected(self):
        with self.assertRaises(ValueError):
            rider_updates('netkeiba:05339', {})
        with self.assertRaises(ValueError):
            rider_updates('jra:005339', {'jra:005339': {'value': .5, 'samples': -1}})


if __name__ == '__main__':
    unittest.main()
