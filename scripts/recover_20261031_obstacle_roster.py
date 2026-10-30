"""Recover one transiently interrupted official obstacle roster; no prediction changes."""
import hashlib
import json
import time
from pathlib import Path
from urllib.error import HTTPError
import forecast_20261031_1101_four_model as forecast

def main():
    date,track,race="2026-10-31","京都",4
    for attempt in range(3):
        try:
            urls,seed_sha=forecast.official_race_urls(date,track)
            horses,roster_sha,weather,going,surface,off_at=forecast.parse_official_roster(urls[race],date,track,race)
            secondary,secondary_url,secondary_sha=forecast.parse_internal_roster(date,track,forecast.MEETINGS[date][track]["code"],race)
            norm=lambda x:forecast.re.sub(r"[\s　]","",x)
            if {h["number"]:norm(h["name"]) for h in horses}!={h["number"]:norm(h["name"]) for h in secondary}:
                raise ValueError("RECOVERED_ROSTER_MISMATCH")
            break
        except HTTPError as exc:
            if exc.code==403: raise
            if attempt==2: raise
            time.sleep(1)
        except Exception:
            if attempt==2: raise
            time.sleep(1)
    result={"schema":"keiba-obstacle-roster-recovery-v1","date":date,"track":track,"race_number":race,
            "captured_at":forecast.dt.datetime.now(forecast.JST).isoformat(),"off_at":off_at,
            "surface":"obstacle","roster_source":urls[race],"roster_sha256":roster_sha,"meeting_seed_sha256":seed_sha,
            "independent_roster_source":secondary_url,"independent_roster_sha256":secondary_sha,
            "declared_runner_count":len(horses),"runners":horses,"weather":weather,"going":going,
            "full_roster_verified":True,"prediction_model_in_domain":False,
            "parent_prediction":"operations/predictions/2026-10-31/preoff_20261031T011832+0900.json",
            "parent_prediction_sha256":"0649328dffc3b50a2a80c79c0ce341ecda713fc2188752fd86930b218f71ea1b",
            "parent_predictions_modified":False}
    stamp=forecast.dt.datetime.now(forecast.JST).strftime("%Y%m%dT%H%M%S%z")
    path=forecast.BASE/"operations/predictions"/date/f"obstacle_roster_recovery_{stamp}.json"
    raw=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    path.write_text(raw,encoding="utf-8")
    assert json.loads(path.read_text())["runners"]==horses
    print(json.dumps({"path":str(path.relative_to(forecast.BASE)),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"declared_runners":len(horses),"verified":True},ensure_ascii=False))
if __name__=="__main__": main()
