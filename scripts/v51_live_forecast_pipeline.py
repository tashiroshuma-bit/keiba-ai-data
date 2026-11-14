"""One-command fail-closed V51 live prediction: official HTML -> roster -> frozen features -> model.

Requires canonical DB and historical publication manifest; never substitutes
research outputs or assumed publication times for official forecasts.
"""
import argparse
import json
from pathlib import Path

try:
    from scripts.v51_official_live_roster import parse_source
    from scripts.v51_frozen_live_feature_builder import build_snapshot
    from scripts.standard_v51_forecast import forecast
except ModuleNotFoundError:
    from v51_official_live_roster import parse_source
    from v51_frozen_live_feature_builder import build_snapshot
    from standard_v51_forecast import forecast

def main():
    p=argparse.ArgumentParser()
    for name in ("html","source-url","observed-at","race","off-at","track",
                 "surface","distance-m","database","overlay","publication-manifest","model","output-dir"):
        p.add_argument("--"+name,required=True)
    a=p.parse_args()
    out=Path(a.output_dir)
    out.mkdir(parents=True,exist_ok=True)
    roster=out/"official_roster.json"
    snapshot=out/"frozen_v51_snapshot.json"
    predictions=out/"official_v51_forecast.json"
    for pth in (roster,snapshot,predictions):
        if pth.exists():
            raise FileExistsError("FORECAST_OUTPUT_MUST_NOT_OVERWRITE:"+str(pth))
    parsed=parse_source(Path(a.html).read_bytes(),url=a.source_url,
                        observed_at=a.observed_at,race=a.race,off_at=a.off_at,
                        track=a.track,surface=a.surface,distance_m=int(a.distance_m))
    roster.write_text(json.dumps(parsed,ensure_ascii=False,indent=2)+"\n")
    features=build_snapshot(a.database,a.overlay,roster,a.publication_manifest,a.model)
    snapshot.write_text(json.dumps(features,ensure_ascii=False,indent=2)+"\n")
    result=forecast(snapshot,a.database,predictions,model_path=a.model)
    print(json.dumps({"status":result["status"],"version":result["version"],
                      "races":len(result["races"]),"forecast":str(predictions)},
                     ensure_ascii=False))
if __name__=="__main__":
    main()
