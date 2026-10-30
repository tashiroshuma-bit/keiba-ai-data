"""Read-only audit of five user-supplied netkeiba cards against saved research inputs."""
import datetime as dt, hashlib, json, re
from pathlib import Path
from urllib.request import Request,urlopen
from bs4 import BeautifulSoup
BASE=Path(__file__).resolve().parents[1]
SAVED=BASE/"operations/predictions/2026-10-31/preoff_20261031T011832+0900.json"
data=json.loads(SAVED.read_text())
targets=[("京都3R","202608041003"),("東京3R","202605041003"),("東京7R","202605041007"),("京都9R","202608041009"),("東京10R","202605041010")]
out={"captured_at":dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),"saved_input_sha256":hashlib.sha256(SAVED.read_bytes()).hexdigest(),"races":[]}
for name,code in targets:
 r=next(r for r in data["races"] if r["race"]==name)
 entry={"race":name,"netkeiba_url":"https://race.sp.netkeiba.com/race/shutuba.html?race_id="+code,"saved_count":r["runner_count"]}
 for kind,url in (("netkeiba",entry["netkeiba_url"]),("jra",r["roster_source"])):
  try:
   with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=15) as response:
    raw=response.read()
   soup=BeautifulSoup(raw,"html.parser")
   tables=[]
   for table in soup.find_all("table"):
    text=table.get_text(" ",strip=True)
    if "馬名" not in text:continue
    rows=[]
    for row in table.find_all("tr"):
     cells=row.find_all(["th","td"],recursive=False)
     if cells:rows.append([{"class":c.get("class",[]),"text":c.get_text(" ",strip=True)} for c in cells])
    if rows:tables.append(rows)
   entry[kind]={"url":url,"sha256":hashlib.sha256(raw).hexdigest(),"title":soup.title.get_text(" ",strip=True) if soup.title else None,"text_head":soup.get_text(" ",strip=True)[-24000:][:10000],"tables":tables}
  except Exception as exc:entry[kind]={"url":url,"error":str(exc)}
 out["races"].append(entry)
 print(name,{k:("error" if "error" in entry[k] else len(entry[k]["tables"])) for k in ("netkeiba","jra")},flush=True)
path=BASE/"reports/weekend_20261031_1101/NETKEIBA_CARD_AUDIT_RAW_20261031.json"
path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
print("SAVED",str(path.relative_to(BASE)),flush=True)
