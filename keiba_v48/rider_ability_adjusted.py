"""As-of rider residual after controlling for the horse's pre-race score.

Only full historical fields are used. The score is observational, not a
causal estimate. Missing field/horse score is excluded, not imputed from
post-race outcomes.
"""
from collections import defaultdict
from datetime import datetime, timezone
from math import exp


def ts(value):
    dt=value if isinstance(value,datetime) else datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone required")
    return dt.astimezone(timezone.utc)


def rider_residuals(history, cutoff, context, prior_n=30):
    cutoff=ts(cutoff)
    races=defaultdict(list)
    for row in history:
        if not all(row.get(k) is not None for k in
                   ("race_id","jockey_id","horse_pre_race_score","off_timestamp",
                    "result_available_at","field_size","finish_position")):
            continue
        if row.get("availability_basis","").startswith("assumed_"):
            continue
        off=ts(row["off_timestamp"])
        published=ts(row["result_available_at"])
        if off>=cutoff or published>cutoff or published<off:
            continue
        races[row["race_id"]].append(row)
    by_rider=defaultdict(list)
    included_races=0
    for rows in races.values():
        field=int(rows[0]["field_size"])
        if field<3 or len(rows)!=field or len({r.get("horse_id") for r in rows})!=field:
            continue
        if any(int(r["field_size"])!=field for r in rows):
            continue
        positions=[r["finish_position"] for r in rows]
        if any(not isinstance(x,int) or x<1 or x>field for x in positions):
            continue
        scores=[float(r["horse_pre_race_score"]) for r in rows]
        mean=sum(scores)/field
        # Rank-order expectation is centered within each historical race.
        raw=[1/(1+exp(-max(-40,min(40,4*(s-mean))))) for s in scores]
        center=sum(raw)/field
        included_races+=1
        for r,expected in zip(rows,raw):
            realized=(field-r["finish_position"])/(field-1)
            residual=realized-(expected-center+.5)
            by_rider[r["jockey_id"]].append((residual,r))
    def summarize(rows):
        n=len(rows)
        return dict(starts=n,score=sum(v for v,_ in rows)/(n+prior_n),
                    confidence=n/(n+prior_n))
    result={}
    for rider,observations in by_rider.items():
        surface=[x for x in observations if x[1].get("surface")==context.get("surface") and context.get("surface") is not None]
        distance=[x for x in surface if x[1].get("distance_m") is not None and context.get("distance_m") is not None and abs(float(x[1]["distance_m"])-float(context["distance_m"]))<=200]
        track=[x for x in surface if x[1].get("track")==context.get("track") and context.get("track") is not None]
        result[rider]=dict(overall=summarize(observations),surface=summarize(surface),
                           distance=summarize(distance),track=summarize(track))
    return dict(riders=result,complete_fields=included_races,method="observational_asof_residual")
