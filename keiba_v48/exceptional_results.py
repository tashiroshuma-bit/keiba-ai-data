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
    sizes = [_rank(row.get('expected_runners', row.get('field_size'))) for row in active]
    if not sizes or any(size is None for size in sizes):
        reasons.append('missing_expected_runner_count')
    elif any(size != len(active) for size in sizes):
        reasons.append('incomplete_expected_runner_count')
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


def ticket_hit(rows, selected, kind):
    """Official top-three slot feasibility, including non-winning dead heats.

    Two third-place horses cannot occupy the single third-place slot together.
    Two horses tied second may occupy second and third together. Require a
    validated complete ranking rather than treating every rank <=3 as a hit.
    """
    size = {'win': 1, 'wide': 2, 'trio': 3}.get(kind)
    if size is None or len(selected) != size or len(set(selected)) != size:
        raise ValueError('invalid ticket kind or selection')
    if not competition_ranks_are_complete(rows):
        raise ValueError('unsupported or incomplete result ranks')
    if any(isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(rows) for i in selected):
        raise ValueError('invalid selected runner index')
    ranks = [_rank(rows[i].get('finish_position')) for i in selected]
    if kind == 'win':
        return ranks[0] == 1
    if any(rank is None or rank > 3 for rank in ranks):
        return False
    return all(count <= 4 - rank for rank, count in collections.Counter(ranks).items())
