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


def integrate_histories(sources, identities=None, allow_assumed_availability=False, allow_missing_jockey=False):
    """Merge any number of graded/non-graded history exports without last-write wins."""
    identities = identities or IdentityMap()
    merged = {}
    for source in sources:
        for row in source:
            r = dict(row)
            if r.get('availability_basis', '').startswith('assumed_') and not allow_assumed_availability:
                raise ValueError('assumed publication availability is research-only')
            for key in ('race_id', 'horse_id', 'off_timestamp',
                        'result_available_at', 'source_url', 'distance_m', 'surface'):
                if not r.get(key):
                    raise ValueError(f'history missing {key}')
            if not r['source_url'].startswith(('https://', 'http://')):
                raise ValueError('history provenance required')
            if not r.get('jockey_id') and not allow_missing_jockey:
                raise ValueError('history missing jockey_id')
            for kind in ('horse', 'jockey'):
                if kind == 'jockey' and not r.get('jockey_id') and allow_missing_jockey:
                    r['jockey_id'] = None
                    continue
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
    def __init__(self, rows, identities=None, allow_assumed_availability=False, allow_missing_jockey=False):
        self.allow_missing_jockey = allow_missing_jockey
        self.rows = integrate_histories([rows], identities, allow_assumed_availability, allow_missing_jockey)
        self.groups = {kind: collections.defaultdict(list) for kind in ('horse', 'jockey')}
        self.times = {}
        self.available_times = {}
        for row in self.rows:
            for kind in self.groups:
                if row.get(kind + '_id'):
                    self.groups[kind][row[kind + '_id']].append(row)
        for kind, groups in self.groups.items():
            for identity, group in groups.items():
                self.times[kind, identity] = [timestamp(r['off_timestamp']).timestamp() for r in group]
                self.available_times[kind, identity] = [timestamp(r['result_available_at']).timestamp() for r in group]

        self.jockey_prefix = {}
        self.jockey_race_events = collections.defaultdict(list)
        for identity, group in self.groups['jockey'].items():
            events = sorted((timestamp(r['result_available_at']).timestamp(), int(finish(r)<=3), r['race_id']) for r in group if finish(r))
            total = [0]
            for at, hit, rid in events:
                total.append(total[-1]+hit)
                self.jockey_race_events[rid].append((identity,at,hit))
            self.jockey_prefix[identity] = ([x[0] for x in events],total)

    def jockey_form(self, identity, race_id, off, cutoff):
        if cutoff >= off:
            return shrink(self.prior('jockey',identity,race_id,off,cutoff),lambda r:True,strength=20)
        times, prefix = self.jockey_prefix.get(identity,([], [0]))
        n = bisect.bisect_right(times,cutoff.timestamp()); hits=prefix[n]
        for jid,at,hit in self.jockey_race_events.get(race_id,[]):
            if jid == identity and at <= cutoff.timestamp(): n-=1; hits-=hit
        return (hits+5)/(n+20),n

    def prior(self, kind, identity, race_id, off, cutoff):
        group = self.groups[kind].get(identity, [])
        end = bisect.bisect_left(self.times.get((kind, identity), []), off.timestamp())
        available = self.available_times.get((kind, identity), [])
        boundary = cutoff.timestamp()
        return [group[i] for i in range(end) if group[i]['race_id'] != race_id and available[i] <= boundary]


def finish(r):
    value = number(r.get('finish_position'))
    return int(value) if value and value.is_integer() and value >= 1 else None


def shrink(rows, predicate, strength=5, prior=0.25):
    values = [float(finish(r) <= 3) for r in rows if finish(r) and predicate(r)]
    return (sum(values) + strength * prior) / (len(values) + strength), len(values)


def front_status(row):
    size=number(row.get('field_size'));corner=number(row.get('corner4_position'))
    if size is None or size<=1 or corner is None:return None
    bounds=row.get('corner4_range')
    if bounds:
        lo,hi=map(float,bounds)
        if not 1<=lo<=hi<=size:raise ValueError('invalid corner group range')
        if (lo-1)/(size-1)<=.35<(hi-1)/(size-1):return None
    return (corner-1)/(size-1)<=.35


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
        jockey = (None if index.allow_missing_jockey and not r.get('jockey_id')
                  else identities.resolve('jockey', r['jockey_id']))
        off = timestamp(r['off_timestamp'])
        cutoff = off - dt.timedelta(minutes=cutoff_minutes)
        if cutoff_minutes < 0:
            raise ValueError('negative cutoff')
        # No target-race, future, or late-published results; indexed by stable ID.
        h = index.prior('horse', horse, r['race_id'], off, cutoff)
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
        jockey_form, _ = index.jockey_form(jockey, r['race_id'], off, cutoff)
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
                    if front_status(x) is not None:corners.append((corner - 1) / (size - 1))
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
                       'jockey_identity_missing': jockey is None,
                       'previous_final_win_odds': number(h[-1].get('final_win_odds')) if h else None,
                       'front_rate': front, 'closing_quality': values[8]})
    return output

ENRICHED_FEATURE_NAMES = FEATURE_NAMES + ('margin_quality','margin_observed','opponent_quality','opponent_observed','horse_jockey_form','gate_fraction','gate_observed','same_day_front_bias','same_day_bias_observed','nonfinish_rate')
