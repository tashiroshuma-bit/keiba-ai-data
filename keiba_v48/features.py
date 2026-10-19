"""All-start, point-in-time features. Missing observations are explicit, never final odds.
IDs are opaque, namespace-qualified source IDs; aliases require reviewed evidence.
"""
import collections
import bisect
import datetime as dt
import math
import re


def timestamp(value):
    value = dt.datetime.fromisoformat(value)
    if value.tzinfo is None:
        raise ValueError('timezone offset required')
    return value


def number(value, default=None):
    if value in (None, ''):
        return default
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('non-finite number')
    return value


class IdentityMap:
    def __init__(self, aliases=()):
        self.aliases = {}
        for a in aliases:
            if a.get('verified') != 'yes' or not a.get('source_url', '').startswith('https://'):
                raise ValueError('identity mapping requires reviewed provenance')
            key = (a['kind'], a['alias'])
            canonical = a['canonical']
            if key in self.aliases and self.aliases[key] != canonical:
                raise ValueError('ambiguous identity alias')
            self.aliases[key] = canonical

    def resolve(self, kind, value):
        value = self.aliases.get((kind, value), value)
        if not re.fullmatch(r'[a-z][a-z0-9_-]*:[A-Za-z0-9_-]+', value or ''):
            raise ValueError(f'{kind} ID must be namespace:source_id; names are not IDs')
        return value


def integrate_histories(sources, identities=None, allow_assumed_availability=False):
    """Merge any number of graded/non-graded history exports without last-write wins."""
    identities = identities or IdentityMap()
    merged = {}
    for source in sources:
        for row in source:
            r = dict(row)
            if r.get('availability_basis', '').startswith('assumed_') and not allow_assumed_availability:
                raise ValueError('assumed publication availability is research-only')
            for key in ('race_id', 'horse_id', 'jockey_id', 'off_timestamp',
                        'result_available_at', 'source_url', 'distance_m', 'surface'):
                if not r.get(key):
                    raise ValueError(f'history missing {key}')
            if not r['source_url'].startswith(('https://', 'http://')):
                raise ValueError('history provenance required')
            for kind in ('horse', 'jockey'):
                r[kind + '_id'] = identities.resolve(kind, r[kind + '_id'])
            if timestamp(r['result_available_at']) < timestamp(r['off_timestamp']):
                raise ValueError('result published before race')
            if number(r['distance_m']) <= 0:
                raise ValueError('invalid distance')
            key = (r['race_id'], r['horse_id'])
            if key in merged:
                old = merged[key]
                # Different source URLs may corroborate the same result.
                for field in set(old) | set(r):
                    if field == 'source_url':
                        continue
                    if old.get(field) not in (None, '') and r.get(field) not in (None, '') and str(old[field]) != str(r[field]):
                        raise ValueError(f'conflicting history {key}: {field}')
                r = {**old, **{k: v for k, v in r.items() if v not in (None, '')}}
                r['source_url'] = old['source_url']
            merged[key] = r
    return sorted(merged.values(), key=lambda r: (timestamp(r['off_timestamp']), r['race_id'], r['horse_id']))


class HistoryIndex:
    """Resolve/deduplicate once, then restrict queries to the relevant horse/jockey."""
    def __init__(self, rows, identities=None, allow_assumed_availability=False):
        self.rows = integrate_histories([rows], identities, allow_assumed_availability)
        self.groups = {kind: collections.defaultdict(list) for kind in ('horse', 'jockey')}
        self.times = {}
        for row in self.rows:
            for kind in self.groups:
                self.groups[kind][row[kind + '_id']].append(row)
        for kind, groups in self.groups.items():
            for identity, group in groups.items():
                self.times[kind, identity] = [timestamp(r['off_timestamp']) for r in group]

    def prior(self, kind, identity, race_id, off, cutoff):
        group = self.groups[kind].get(identity, [])
        end = bisect.bisect_left(self.times.get((kind, identity), []), off)
        return [h for h in group[:end] if h['race_id'] != race_id
                and timestamp(h['result_available_at']) <= cutoff]


def finish(r):
    value = number(r.get('finish_position'))
    return int(value) if value and value.is_integer() and value >= 1 else None


def shrink(rows, predicate, strength=5, prior=0.25):
    values = [float(finish(r) <= 3) for r in rows if finish(r) and predicate(r)]
    return (sum(values) + strength * prior) / (len(values) + strength), len(values)


FEATURE_NAMES = ('ability', 'recent_quality', 'rest_log', 'course_form', 'going_form',
                 'distance_form', 'jockey_form', 'front_rate', 'closing_quality',
                 'weight_delta', 'history_log', 'speed_quality', 'speed_observed')


def build_features(history, runners, identities=None, cutoff_minutes=5):
    identities = identities or IdentityMap()
    index = history if isinstance(history, HistoryIndex) else HistoryIndex(history, identities)
    output = []
    for raw in runners:
        r = dict(raw)
        horse = identities.resolve('horse', r['horse_id'])
        jockey = identities.resolve('jockey', r['jockey_id'])
        off = timestamp(r['off_timestamp'])
        cutoff = off - dt.timedelta(minutes=cutoff_minutes)
        if cutoff_minutes < 0:
            raise ValueError('negative cutoff')
        # No target-race, future, or late-published results; indexed by stable ID.
        h = index.prior('horse', horse, r['race_id'], off, cutoff)
        j = index.prior('jockey', jockey, r['race_id'], off, cutoff)
        recent = [x for x in h if finish(x)][-3:]
        qualities = []
        for x in recent:
            size = number(x.get('field_size'))
            if size and size >= finish(x) and size > 1:
                # Class levels are supplied ordinal 0..6 (maiden through G1).
                level = number(x.get('class_level'), 0)
                if not 0 <= level <= 6:
                    raise ValueError('class_level must be 0..6')
                qualities.append(1 - (finish(x) - 1) / (size - 1) + level / 12)
        ability, _ = shrink(h, lambda x: True)
        course, nc = shrink(h, lambda x: bool(r.get('track')) and x.get('track') == r['track'] and x['surface'] == r.get('surface'))
        going, ng = shrink(h, lambda x: bool(r.get('going')) and x.get('going') == r['going'] and x['surface'] == r.get('surface'))
        distance, nd = shrink(h, lambda x: x['surface'] == r.get('surface') and abs(float(x['distance_m']) - float(r['distance_m'])) <= 200)
        jockey_form, _ = shrink(j, lambda x: True, strength=20)
        corners = []
        closing = []
        speeds = []
        for x in h[-5:]:
            size = number(x.get('field_size'))
            corner = number(x.get('corner4_position'))
            last_rank = number(x.get('last_3f_rank'))
            if size and size > 1:
                if corner is not None:
                    if not 1 <= corner <= size:
                        raise ValueError('invalid corner position')
                    corners.append((corner - 1) / (size - 1))
                if last_rank is not None:
                    if not 1 <= last_rank <= size:
                        raise ValueError('invalid closing rank')
                    closing.append(1 - (last_rank - 1) / (size - 1))
            if x['surface'] == r.get('surface') and abs(float(x['distance_m']) - float(r['distance_m'])) <= 200:
                z = number(x.get('relative_speed_z'))
                if z is not None:
                    speeds.append(max(-3, min(3, z)))
        rest = max(0, (off - timestamp(h[-1]['off_timestamp'])).days) if h else 0
        weight = number(r.get('carried_weight'))
        last_weight = number(h[-1].get('carried_weight')) if h else None
        front = sum(v <= .35 for v in corners) / len(corners) if corners else .5
        values = [ability, sum(qualities) / len(qualities) if qualities else .5,
                  math.log1p(min(rest, 730)) / 7, course, going, distance, jockey_form,
                  front, sum(closing) / len(closing) if closing else .5,
                  (weight - last_weight) / 10 if weight is not None and last_weight is not None else 0,
                  math.log1p(len(h)) / 5, sum(speeds) / len(speeds) if speeds else 0, float(bool(speeds))]
        output.append({'race_id': r['race_id'], 'horse_id': horse, 'jockey_id': jockey,
                       'horse_number': str(r['horse_number']), 'group': f"{r.get('track', '')}/{r.get('surface', '')}",
                       'cutoff_timestamp': cutoff.isoformat(), 'values': values,
                       'history_starts': len(h), 'course_samples': nc, 'going_samples': ng,
                       'distance_samples': nd, 'style_observed': bool(corners),
                       'current_going_known': bool(r.get('going')), 'recent_quality_samples': len(qualities),
                       'front_rate': front, 'closing_quality': values[8]})
    return output
