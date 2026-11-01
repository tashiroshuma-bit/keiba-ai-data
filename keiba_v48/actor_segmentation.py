"""Leakage-safe horse/jockey feature segmentation for rank-model research.

No scores are converted into winning probabilities. Categories are mutually
exclusive for surface, with condition-specific support and explicit missingness.
"""
import math

SURFACES = ("turf", "dirt", "jump")


def _distance_band(meters):
    value = float(meters)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("invalid distance")
    if value < 1400:
        return "sprint"
    if value < 1800:
        return "mile"
    if value < 2200:
        return "middle"
    if value < 2800:
        return "long"
    return "extended"


def _prior_observations(rows, cutoff, entity_id, kind):
    from features import timestamp, finish
    if kind not in ("horse", "jockey"):
        raise ValueError("kind must be horse or jockey")
    if not entity_id or str(entity_id).startswith("unlinked:"):
        return []
    boundary = timestamp(cutoff) if isinstance(cutoff, str) else cutoff
    out = []
    for row in rows:
        if row.get(kind + "_id") != entity_id:
            continue
        if row.get("availability_basis", "").startswith("assumed_"):
            raise ValueError("assumed historical availability cannot be live evidence")
        off = timestamp(row["off_timestamp"])
        available = timestamp(row["result_available_at"])
        if available < off:
            raise ValueError("invalid result observation time")
        if off >= boundary or available > boundary:
            continue
        if finish(row) is None and row.get("runner_status") != "nonfinisher":
            continue
        out.append(row)
    return sorted(out, key=lambda row: (timestamp(row["off_timestamp"]), row["race_id"]))


def _summary(rows):
    from features import finish
    n = len(rows)
    if not n:
        return dict(starts=0, wins=0, top3=0, win_rate=None, top3_rate=None,
                    win_shrunk=None, top3_shrunk=None, support=0.)
    wins = sum(finish(row) == 1 for row in rows)
    top3 = sum(finish(row) in (1, 2, 3) for row in rows)
    # Neutral prior used only for descriptive stability, not calibrated P(win).
    return dict(starts=n, wins=wins, top3=top3, win_rate=wins/n,
                top3_rate=top3/n, win_shrunk=(wins+0.5)/(n+5),
                top3_shrunk=(top3+1.5)/(n+5), support=n/(n+5))


def segment_actor(rows, cutoff, entity_id, kind, context):
    """Return separately supported conditions without mixing horse and jockey IDs."""
    history = _prior_observations(rows, cutoff, entity_id, kind)
    surface = context.get("surface")
    track = context.get("track")
    distance = context.get("distance_m")
    if surface not in SURFACES or distance is None:
        raise ValueError("surface and distance required")
    band = _distance_band(distance)
    same_surface = [r for r in history if r.get("surface") == surface]
    same_band = [r for r in same_surface if r.get("distance_m") is not None
                 and _distance_band(r["distance_m"]) == band]
    same_course = [r for r in same_surface if r.get("track") == track]
    recent = history[-5:] if kind == "horse" else history[-30:]
    return dict(kind=kind, identity=entity_id, cutoff=str(cutoff),
                distance_band=band,
                overall=_summary(history),
                same_surface=_summary(same_surface),
                same_distance_band=_summary(same_band),
                same_track_surface=_summary(same_course),
                recent=_summary(recent),
                surface_switch=bool(history and history[-1].get("surface") != surface),
                no_history=not bool(history),
                use_as_probability=False,
                note="Descriptive as-of segmentation; coefficients require prior-year fitting.")
