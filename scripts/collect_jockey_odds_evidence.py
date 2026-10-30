"""Collect source-linked card identities and public odds script evidence."""
import json,hashlib,datetime as dt,re
from pathlib import Path
from urllib.request import urlopen,Request
from urllib.parse import urljoin
from bs4 import BeautifulSoup
root=Path(__file__).resolve().parents[1]
saved=json.loads((root/"operations/predictions/2026-10-31/preoff_20261031T011832+0900.json").read_text())
targets=[("京都3R","202608041003"),("東京3R","202605041003"),("東京7R","202605041007"),("京都9R","202608041009"),("東京10R","202605041010")]
out={"races":[],"scripts":[]}
def fetch(url):
 with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=20) as r: raw=r.read()
 return raw,dt.datetime.now(dt.timezone.utc).isoformat()
for name,code in targets:
 old=next(r for r in saved["races"] if r["race"]==name)
 item={"race":name,"code":code}
 for kind,url in [("jra",old["roster_source"]),("netkeiba","https://race.sp.netkeiba.com/race/shutuba.html?race_id="+code)]:
  try:
   raw,at=fetch(url);s=BeautifulSoup(raw,"html.parser")
   item[kind]={"url":url,"at":at,"sha256":hashlib.sha256(raw).hexdigest(),"text":s.get_text(" ",strip=True),"rows":[{"text":r.get_text(" ",strip=True),"cells":[{"class":c.get("class",[]),"text":c.get_text(" ",strip=True)} for c in r.find_all(["td","th"],recursive=False)],"links":[{"text":a.get_text(" ",strip=True),"href":urljoin(url,a["href"]),"onclick":a.get("onclick")} for a in r.find_all("a",href=True)]} for r in s.select("tr")],"scripts":[{"src":urljoin(url,x["src"])} if x.get("src") else {"inline":x.get_text()} for x in s.find_all("script")]}
  except Exception as e:item[kind]={"error":str(e)}
 out["races"].append(item);print(name,flush=True)
# Inspect actual linked JavaScript. This does not invent odds endpoints.
first=out["races"][0].get("netkeiba",{})
for tag in first.get("scripts",[]):
 url=tag.get("src")
 if not url or not any(k in url.lower() for k in ("jquery.odds_update",)):continue
 try:
  raw,at=fetch(url);out["scripts"].append({"url":url,"at":at,"text":raw.decode("utf-8",errors="replace")})
 except Exception as e:out["scripts"].append({"url":url,"error":str(e)})
out["odds"]=[]
from urllib.parse import urlencode
for name,code in targets:
 params={"pid":"api_get_jra_odds","input":"UTF-8","output":"jsonp","race_id":code,"type":1,"action":"init","sort":"odds","compress":1,"callback":"odds_callback"}
 url="https://race.sp.netkeiba.com/?"+urlencode(params)
 try:
  raw,at=fetch(url);out["odds"].append({"race":name,"url":url,"at":at,"sha256":hashlib.sha256(raw).hexdigest(),"text":raw.decode("utf-8",errors="replace")})
 except Exception as e:out["odds"].append({"race":name,"url":url,"error":str(e)})
p=root/"reports/weekend_20261031_1101/JOCKEY_ODDS_SOURCE_EVIDENCE.json";p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
