from urllib.request import Request,urlopen
from bs4 import BeautifulSoup
url="https://sports.yahoo.co.jp/keiba/race/result/2507010101"
with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=20) as resp:
 html=resp.read()
soup=BeautifulSoup(html,"html.parser")
print("TITLE:",soup.title.get_text(" ",strip=True)[:120])
for table in soup.select("table")[:10]:
 print("TABLE:",(table.get("class") or []),table.get_text(" ",strip=True)[:150])
 for tr in table.select("tr")[:4]:
  cs=tr.find_all(["th","td"],recursive=False)
  print("ROW:",[c.get_text(" ",strip=True)[:85] for c in cs])
