"""Strict eligibility rules for win-model fields with exceptional placings."""
import collections
import math


def _rank(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 1 or not number.is_integer():
        return None
    return int(number)


def competition_ranks_are_complete(rows):
    """Accept standard competition ranks, including non-winning dead heats.

    Examples: 1,2,3,3,5 is valid; 1,2,3,3,4 and 1,1,3 are not.
    The win model requires exactly one winner, so a first-place dead heat stays
    quarantined even if the remaining competition ranks are well formed.
    """
    ranks = []
    for row in rows:
        status = row.get('runner_status')
        rank = _rank(row.get('finish_position'))
        if status == 'nonstarter':
            continue
        if status == 'nonfinisher':
            if rank is not None:
                return False
            continue
        if status not in (None, 'finished') or rank is None:
            return False
        ranks.append(rank)
    if len(ranks) < 3 or ranks.count(1) != 1:
        return False
    counts = collections.Counter(ranks)
    expected = 1
    for rank in sorted(counts):
        if rank != expected:
            return False
        expected += counts[rank]
    return True


def field_rejection_reasons(rows, unsafe_source=False):
    reasons = []
    active = [row for row in rows if row.get('runner_status') != 'nonstarter']
    if unsafe_source:
        reasons.append('unverified_source_exception')
    if len(active) < 3:
        reasons.append('field_lt3')
    if not competition_ranks_are_complete(active):
        reasons.append('outcome_not_unique_winner_competition_ranks')
    identities = [row.get('horse_id') for row in active]
    if not all(identities):
        reasons.append('missing_horse_identity')
    elif len(set(identities)) != len(identities):
        reasons.append('duplicate_horse_identity')
    for key in ('off_timestamp', 'distance_m', 'surface'):
        if any(not row.get(key) for row in active):
            reasons.append('missing_' + key)
    return reasons
