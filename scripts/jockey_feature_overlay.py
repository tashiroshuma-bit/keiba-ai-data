"""Restore the frozen model's learned rider feature in a career-proxy shadow.

This does not make the remaining mean-imputed inputs observed history, and
does not establish calibration or improve the model's measured accuracy.
"""
import math


def rider_updates(jockey_id, statistics):
    if jockey_id is None:
        return {'jockey_form': .25, 'jockey_identity_missing': 1}, 0
    if not jockey_id.startswith('jra:'):
        raise ValueError('source-attested JRA jockey ID required')
    record = statistics.get(jockey_id)
    if record is None:
        return {'jockey_form': .25, 'jockey_identity_missing': 0}, 0
    value, samples = record['value'], record['samples']
    if not isinstance(samples, int) or samples < 0 or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('invalid observed rider feature')
    return {'jockey_form': value, 'jockey_identity_missing': 0}, samples


def overlay(features, horses, names, statistics):
    if len(features) != len(horses):
        raise ValueError('field mismatch')
    indexes = {name: i for i, name in enumerate(names)}
    result = []
    for feature, horse in zip(features, horses):
        values = list(feature['values'])
        updates, samples = rider_updates(horse.get('jockey_id'), statistics)
        for name, value in updates.items():
            values[indexes[name]] = value
        result.append({**feature, 'values': values, 'jockey_history_samples': samples})
    return result
