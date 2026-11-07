import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
paths=[
"operations/results/2026-10-31/four_model_settlement_20261031T192204+0900.json",
"operations/results/2026-11-01/four_model_settlement_20261101T194949+0900.json",
"reports/weekend_20261031_1101/ALL_FLAT_CARD_ODDS_20261030T183252Z.json",
"reports/weekend_20261031_1101/ALL_FLAT_RIDER_RECALC_20261031T033252.json",
"reports/update_20261101/ENTRY_ODDS_OBSERVATIONS.json",
"reports/odds_refresh_20261101_morning/PREDICTIONS.json",
"operations/results/2026-10-25/weekend_observations.json",
"keiba_v48/reports/completion/paired_predictions_lag7.json",
]
def preview(value):
 if isinstance(value,dict):return {"type":"dict","keys":list(value)[:35],"sample":{k:preview(v) for k,v in list(value.items())[:5]}}
 if isinstance(value,list):return {"type":"list","len":len(value),"first":preview(value[0]) if value else None}
 if isinstance(value,str):return value[:85]
 return value
for p in paths:
 try:
  x=json.loads((ROOT/p).read_text())
  print(json.dumps({"path":p,"structure":preview(x)},ensure_ascii=False)[:3100],flush=True)
 except Exception as e:print(json.dumps({"path":p,"error":repr(e)}),flush=True)

from bs4 import BeautifulSoup
from urllib.request import urlopen,Request
for p in paths[:2]:
 x=json.loads((ROOT/p).read_text())
 first=x["official_sources"][0]
 try:
  with urlopen(Request(first["source_url"],headers={"User-Agent":"Mozilla/5.0"}),timeout=15) as fh:html=fh.read()
  soup=BeautifulSoup(html,"html.parser")
  for tr in soup.find_all("tr")[:35]:
   cells=[z.get_text(" ",strip=True) for z in tr.find_all(["td","th"],recursive=False)]
   if len(cells)>3 and cells[0].strip() in ("1","2","3","4"):
    print(json.dumps({"source":p,"url":first["source_url"],"cells":cells[:15]},ensure_ascii=False)[:1900],flush=True)
 except Exception as e:print(json.dumps({"source":p,"http_error":str(e)}),flush=True)
