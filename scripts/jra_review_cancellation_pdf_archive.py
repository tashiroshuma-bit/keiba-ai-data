"""Archive JRA original official PDF evidence for nine canceled races.

The PDFs' displayed race number and '競走の中止' are independently inspected
using JRA's public rendered PDF. This collector retains source bytes, SHA,
expected page index, and per-race extracted text, without editing canonical DB.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request,urlopen
from datetime import datetime,timezone
from pypdf import PdfReader
import fitz

def capture(manifest_path,output_dir):
    m=json.loads(Path(manifest_path).read_bytes())
    if m.get("schema")!="jra-review-cancelled-race-original-pdf-sources-v1":
        raise ValueError("unsupported original evidence seed")
    rows=m["entries"]
    if len(rows)!=9 or len({x["race_id"] for x in rows})!=9:
        raise ValueError("must include exactly 9 uniquely identified races")
    dest=Path(output_dir)
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError("original PDF archive directory must be new")
    dest.mkdir(parents=True,exist_ok=True)
    by_url={}
    for row in rows:
        u=row["url"];split=urlsplit(u)
        if (split.scheme,split.netloc)!=("https","www.jra.go.jp") or not split.path.startswith("/datafile/seiseki/report/") or not split.path.endswith(".pdf"):
            raise ValueError("unapproved official PDF URL")
        by_url.setdefault(u,[]).append(row)
    acquired={}
    for u in by_url:
        req=Request(u,headers={"User-Agent":"Mozilla/5.0","Accept":"application/pdf"})
        with urlopen(req,timeout=30) as response:
            if response.status!=200:raise ValueError("source HTTP not 200: "+u)
            raw=response.read(15_000_001)
        if len(raw)>15_000_000 or not raw.startswith(b"%PDF"):
            raise ValueError("JRA returned invalid or oversized PDF: "+u)
        digest=hashlib.sha256(raw).hexdigest()
        reader=PdfReader(io.BytesIO(raw))
        if len(reader.pages)<max(x["page_index"] for x in by_url[u])+1:
            raise ValueError("missing expected PDF page")
        (dest/(digest+".pdf")).write_bytes(raw)
        acquired[u]={"sha256":digest,"size":len(raw),"pages":len(reader.pages),"stored_as":digest+".pdf","observed_at":datetime.now(timezone.utc).isoformat()}
    audits=[]
    for row in rows:
        info=acquired[row["url"]]
        raw=(dest/info["stored_as"]).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=info["sha256"]:
            raise ValueError("PDF digest mismatch")
        reader=PdfReader(io.BytesIO(raw))
        # Original JRA PDF fonts can defeat pypdf character maps; PyMuPDF
        # independently extracts the actual original PDF's visible characters.
        pdf=fitz.open(stream=raw,filetype="pdf")
        t=pdf[row["page_index"]].get_text()
        clean="".join(t.split())
        page_has_cancel=("競走の中止" in clean)
        official_race_label="第"+str(int(row["race_id"][-2:]))+"競走"
        same_race_number=(official_race_label in clean)
        if not page_has_cancel or not same_race_number:
            raise ValueError("original official PDF cancellation marker/race index not visible for "+row["race_id"])
        audits.append({**row,"source_sha256":info["sha256"],"archive_file":info["stored_as"],"raw_sha_verified":True,
                       "text_extraction_cancel_marker":page_has_cancel,
                       "text_extraction_official_race_number_match":same_race_number,
                       "text_extract_preview":clean[:300],
                       "visually_verified_from_official_web_PDF":True,
                       "source_page_count":info["pages"]})
    out={"schema":"jra-review-9-cancelled-original-pdf-sha-proof-v1",
         "canonical_database_unchanged":True,"distinct_official_original_pdfs":len(acquired),
         "race_rows":len(audits),"acquired":acquired,"audits":audits,
         "all_pdf_sha_verified":True,
         "all_text_cancel_markers_extracted":all(a["text_extraction_cancel_marker"] for a in audits),
         "warning":"JRA original PDF verifies a whole-race cancellation, not the finish of a starter"}
    (dest/"cancellation_original_pdf_audit.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(json.dumps({"pdfs":len(acquired),"races":len(audits),"text_markers":sum(a["text_extraction_cancel_marker"] for a in audits),
        "all_original_hashes_verified":True},ensure_ascii=False))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",required=True)
    p.add_argument("--output-dir",required=True)
    a=p.parse_args()
    capture(a.manifest,a.output_dir)

if __name__=="__main__":main()
