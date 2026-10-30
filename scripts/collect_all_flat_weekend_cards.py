"""Read-only immutable snapshots for all 46 flat weekend races."""
import datetime as dt,hashlib,json,re
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode,urljoin
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
DATES=["2026-10-31","2026-11-01"]
PRIOR=json.loads((ROOT/"reports/weekend_20261031_1101/JOCKEY_ODDS_SOURCE_20261030T182304Z.json").read_text())
PRIOR_ODDS={r["race"]:r for r in PRIOR["odds"]}
def fetch(url):
 with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=15) as r:raw=r.read()
 return raw,dt.datetime.now(dt.timezone.utc).isoformat()
def snapshot(task):
 date,race=task
 code=date[:4]+("05" if race["track"]=="東京" else "08")+"04"+("10" if date=="2026-10-31" else "11")+str(race["race_number"]).zfill(2)
 out={"date":date,"race":race["race"],"code":code,"old_count":race["runner_count"]}
 for kind,url in [("jra",race["roster_source"]),("netkeiba","https://race.sp.netkeiba.com/race/shutuba.html?race_id="+code)]:
  try:
   raw,at=fetch(url);s=BeautifulSoup(raw,"html.parser")
   out[kind]={"url":url,"at":at,"sha256":hashlib.sha256(raw).hexdigest(),"title":s.title.get_text(" ",strip=True) if s.title else None,"text":s.get_text(" ",strip=True),"rows":[{"text":tr.get_text(" ",strip=True),"cells":[{"class":c.get("class",[]),"text":c.get_text(" ",strip=True)} for c in tr.find_all(["td","th"],recursive=False)],"links":[{"text":a.get_text(" ",strip=True),"href":urljoin(url,a["href"]),"onclick":a.get("onclick")} for a in tr.find_all("a",href=True)]} for tr in s.find_all("tr")]}
  except Exception as e:out[kind]={"url":url,"error":str(e)}
 if date=="2026-10-31" and race["race"] in PRIOR_ODDS:
  out["odds"]=PRIOR_ODDS[race["race"]]
  out["odds"]["reuse_basis"]="Existing observed snapshot; no repeated live request"
 else:
  # Endpoint and parameters were observed in public jquery.odds_update.js.
  params={"pid":"api_get_jra_odds","input":"UTF-8","output":"jsonp","race_id":code,"type":1,"action":"init","sort":"odds","compress":1,"callback":"odds_callback"}
  url="https://race.sp.netkeiba.com/?"+urlencode(params)
  try:
   raw,at=fetch(url);out["odds"]={"url":url,"at":at,"sha256":hashlib.sha256(raw).hexdigest(),"text":raw.decode("utf-8",errors="replace")}
  except Exception as e:out["odds"]={"url":url,"error":str(e)}
 print(date,race["race"],"captured",flush=True)
 return out
tasks=[]
for date in DATES:
 data=json.loads((ROOT/("operations/predictions/"+date+"/preoff_20261031T011832+0900.json")).read_text())
 for race in data["races"]:
  if race["surface"]!="obstacle":tasks.append((date,race))
assert len(tasks)==46
out={"schema":"weekend-public-card-odds-observations-v1","started_at":dt.datetime.now(dt.timezone.utc).isoformat(),"races":[]}
with ThreadPoolExecutor(max_workers=3) as ex:out["races"]=list(ex.map(snapshot,tasks))
out["completed_at"]=dt.datetime.now(dt.timezone.utc).isoformat()
path=ROOT/("reports/weekend_20261031_1101/ALL_FLAT_CARD_ODDS_"+dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")+".json")
path.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
print("SAVED",path.name,flush=True)
