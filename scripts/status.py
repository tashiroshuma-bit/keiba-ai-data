import json,sqlite3
from pathlib import Path
p=Path("jra_2023_2025.sqlite")
if not p.exists():
 report={"error":"database not created"}
else:
 c=sqlite3.connect(p)
 report={}
 for table in ("races","documents","runner_results"):
  try:report[table]=c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
  except sqlite3.Error:report[table]=None
 try:report["pdf_text_extracted"]=c.execute("SELECT COUNT(*) FROM documents WHERE status='text_extracted'").fetchone()[0]
 except sqlite3.Error:pass
 print(json.dumps(report,ensure_ascii=False))
Path("ingest_status.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
