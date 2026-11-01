"""Adapt the immutable 46-race weekend archive to v50's as-of forecast schema.

Never rewrite the archive. Keep provenance and validate all runner joins.
"""
import json
from pathlib import Path


def adapt(source, *, model="D", asof=None):
    if model not in ("A","B","C","D"):
        raise ValueError("unknown frozen model")
    races=[]
    for race in source["races"]:
        if not race.get("number_published"):
            continue
        roster={x["number"]:x for x in race["runners"] if not x.get("withdrawn")}
        horses=[]
        for h in race["models"][model]["horses"]:
            number=h["number"]
            if number not in roster:
                raise ValueError("forecast runner missing from roster: "+race["race"])
            runner=roster[number]
            if not isinstance(number,int):
                raise ValueError("non-integer horse number")
            horses.append({"number":number,"name":h["name"],
                           "jockey_id":runner.get("jockey_id"),
                           "p1":h["p1"]})
        if len(horses)<3 or len({h["number"] for h in horses})!=len(horses):
            raise ValueError("invalid field: "+race["race"])
        races.append({"race":race["date"]+" "+race["race"],
                      "surface":race["surface"],"horses":horses,
                      "original_off_at":race["off_at"]})
    if not races:
        raise ValueError("no eligible races")
    if asof is None:
        asof=source["created_at"]
    return {"asof":asof,"source_schema":source["schema"],
            "source_model":model,"races":races}


def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--model",default="D")
    a=p.parse_args()
    path=Path(a.output)
    if path.exists():
        raise FileExistsError("frozen output cannot be overwritten")
    data=adapt(json.loads(Path(a.input).read_text()),model=a.model)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")


if __name__=="__main__":
    main()
