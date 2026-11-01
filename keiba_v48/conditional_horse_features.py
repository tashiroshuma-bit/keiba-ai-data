"""As-of, evidence-aware conditional horse performance features.

Research/shadow only. Histories must be individual past starts with result
publication time; do not infer missing distance, track, class or going.
"""
from datetime import datetime, timezone


def parse_time(value):
    if isinstance(value,datetime):
        dt=value
    else:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone required")
    return dt.astimezone(timezone.utc)


def distance_band(meters):
    if meters is None:
        return None
    meters=int(meters)
    if meters<=0:
        raise ValueError("invalid distance")
    if meters<=1400:
        return "sprint"
    if meters<=1800:
        return "mile"
    if meters<=2400:
        return "middle"
    return "long"


def condition_key(row, context, kind):
    if kind=="surface":
        return row.get("surface") is not None and row.get("surface")==context.get("surface")
    if kind=="distance":
        a=distance_band(row.get("distance_m"))
        b=distance_band(context.get("distance_m"))
        return a is not None and b is not None and a==b
    if kind=="going":
        return (row.get("surface")==context.get("surface") and
                row.get("going") is not None and row.get("going")==context.get("going"))
    if kind=="track":
        return row.get("track") is not None and row.get("track")==context.get("track")
    raise ValueError("unknown condition")


def weighted_finish(row):
    position=row.get("finish_position")
    if position==1:
        return 1.
    if position==2:
        return .5
    if position==3:
        return .25
    if isinstance(position,int) and position>3:
        return 0.
    return None


def horse_features(history, cutoff, context, prior=.15, prior_n=8):
    boundary=parse_time(cutoff)
    eligible=[]
    for row in history:
        if not row.get("off_timestamp") or not row.get("result_available_at"):
            continue
        if parse_time(row["off_timestamp"])>=boundary or parse_time(row["result_available_at"])>boundary:
            continue
        if parse_time(row["result_available_at"])<parse_time(row["off_timestamp"]):
            continue
        finish=weighted_finish(row)
        if finish is not None:
            eligible.append((row,finish))
    def summary(rows):
        n=len(rows)
        total=sum(v for _,v in rows)
        return dict(starts=n,weighted_podium=total,
                    score=(total+prior*prior_n)/(n+prior_n),
                    confidence=n/(n+prior_n))
    out={"overall":summary(eligible)}
    for kind in ("surface","distance","going","track"):
        subset=[(r,v) for r,v in eligible if condition_key(r,context,kind)]
        out[kind]=summary(subset)
        out[kind]["observed"]=bool(subset)
    # Opponent quality is not inferred from finish; use only documented pre-race
    # opponent scores from each historical race. Missing means unavailable.
    quality=[float(r["opponent_pre_race_score"]) for r,_ in eligible
             if r.get("opponent_pre_race_score") is not None]
    out["opponent_quality"]=dict(observations=len(quality),
                                 mean=sum(quality)/len(quality) if quality else None)
    return out
