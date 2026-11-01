"""Predeclared horse podium, sample confidence and rider-vs-horse residual features.

Research only. A rider's residual is a within-race observational estimate,
not a causal jockey effect. Fit only from prior result-available races.
"""
import collections
import math

def horse_podium(runner, prior_strength=.15, prior_starts=8):
    starts=int(runner.get("starts") or 0)
    wins=int(runner.get("wins") or 0)
    seconds=int(runner.get("seconds") or 0)
    thirds=int(runner.get("thirds") or 0)
    if min(starts,wins,seconds,thirds)<0 or wins+seconds+thirds>starts:
        raise ValueError("invalid horse career counts")
    weighted=(wins+.5*seconds+.25*thirds)
    return dict(value=(weighted+prior_strength*prior_starts)/(starts+prior_starts),
                confidence=starts/(starts+prior_starts),
                starts=starts, raw=None if starts==0 else weighted/starts)


def jockey_residual(history, cutoff, context, prior_starts=30):
    """Estimate rider's surplus vs opponents after controlling for horse strength.

    Each history item must have: result_available_at, off_timestamp,
    jockey_id, horse_pre_race_score, finish_position, field_size, surface,
    distance_m, track. 'horse_pre_race_score' must be calculated as-of that
    historical race, never with future starts.
    """
    from features import timestamp
    boundary=timestamp(cutoff) if isinstance(cutoff,str) else cutoff
    grouped=collections.defaultdict(list)
    for row in history:
        off=timestamp(row["off_timestamp"])
        available=timestamp(row["result_available_at"])
        if off>=boundary or available>boundary or available<off:
            continue
        if row.get("horse_pre_race_score") is None:
            continue
        if not row.get("jockey_id") or not row.get("race_id"):
            continue
        grouped[row["race_id"]].append(row)
    by_jockey=collections.defaultdict(list)
    for race, rows in grouped.items():
        if len(rows)<3 or any(int(r["field_size"])!=len(rows) for r in rows):
            continue
        # Baseline expectation based on horses' pre-race scores within the field.
        scores=[float(r["horse_pre_race_score"]) for r in rows]
        mean=sum(scores)/len(scores)
        for r,s in zip(rows,scores):
            finish=r.get("finish_position")
            if not isinstance(finish,int) or not 1<=finish<=len(rows):
                continue
            realized=(len(rows)-finish)/(len(rows)-1)
            predicted=.5 + .5*math.tanh(s-mean)
            residual=realized-predicted
            same_surface=r.get("surface")==context.get("surface")
            same_distance=(r.get("distance_m") is not None and context.get("distance_m") is not None
                           and abs(float(r["distance_m"])-float(context["distance_m"]))<=200)
            same_track=r.get("track")==context.get("track")
            by_jockey[r["jockey_id"]].append((residual,same_surface,same_distance,same_track))
    out={}
    for jockey,values in by_jockey.items():
        def shrunk(items):
            n=len(items)
            return dict(starts=n,score=sum(items)/(n+prior_starts) if n else 0.,
                        confidence=n/(n+prior_starts))
        out[jockey]=dict(overall=shrunk([v[0] for v in values]),
                         surface=shrunk([v[0] for v in values if v[1]]),
                         distance=shrunk([v[0] for v in values if v[1] and v[2]]),
                         course=shrunk([v[0] for v in values if v[1] and v[3]]))
    return out


def adjust_log_score(p1,runner,rider_residual=None,
                     horse_weight=.8,rider_weight=.4):
    horse=horse_podium(runner)
    rider=rider_residual or {}
    rider_score=(.45*rider.get("overall",{}).get("score",0.)+
                 .3*rider.get("surface",{}).get("score",0.)+
                 .15*rider.get("distance",{}).get("score",0.)+
                 .1*rider.get("course",{}).get("score",0.))
    return math.log(max(p1,1e-300))+horse_weight*(horse["value"]-.15)+rider_weight*rider_score
