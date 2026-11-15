#!/usr/bin/env node
// JRA annual-result PDF inventory; no Python, no race-result inference.
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
const years = process.argv.slice(2).length ? process.argv.slice(2).map(Number) : [2023,2024,2025,2026];
if (years.some(y=>!Number.isInteger(y)||y<2023||y>2026)) throw Error("years must be 2023..2026");
const out="reports/friday_full_backfill/discovery";
await mkdir(out,{recursive:true});
const results=[];
for(const year of years) {
 const url="https://www.jra.go.jp/datafile/seiseki/report/"+year+".html";
 const response=await fetch(url,{redirect:"error",headers:{"User-Agent":"JRA-History-Audit/1.0 (noncommercial)","Accept":"text/html"}});
 if (!response.ok) throw Error("JRA index "+year+" returned "+response.status);
 const html=Buffer.from(await response.arrayBuffer());
 if(!html.length||html.length>4*1024*1024) throw Error("Invalid JRA annual index size");
 const text=html.toString("utf8");
 const links=[...text.matchAll(/href\s*=\s*["']([^"']+\.pdf(?:\?[^"']*)?)["']/gi)]
  .map(x=>new URL(x[1],url).href)
  .filter(u=>new URL(u).hostname==="www.jra.go.jp")
  .filter(u=>new URL(u).pathname.startsWith("/datafile/seiseki/report/"+year+"/"))
  .filter(u=>new URL(u).pathname.toLowerCase().endsWith(".pdf"))
  .filter(u=>/\/[0-9]{4}-[0-9]+[a-z]+[0-9]+\.pdf$/i.test(new URL(u).pathname));
 const unique=[...new Set(links)].sort();
 if(unique.length<200||unique.length>450) throw Error("Unexpected annual result PDF count "+year+"="+unique.length);
 const report={year,source:url,source_sha256:createHash("sha256").update(html).digest("hex"),
 source_bytes:html.length,discovered_at_utc:new Date().toISOString(),
 expected_race_panels_if_all_12:unique.length*12,pdf_count:unique.length,
 entries:unique.map(pdf_url=>({url:pdf_url,filename:path.basename(new URL(pdf_url).pathname)})),
 status:"DOCUMENT_URLS_ONLY_NOT_EXTRACTED"};
 await writeFile(out+"/"+year+".json",JSON.stringify(report,null,2)+"\n");
 await writeFile(out+"/"+year+".html",html);
 console.log("JRA_INDEX_DISCOVERED year="+year+" official_pdf_urls="+unique.length+" index_sha="+report.source_sha256+" (0 full race records verified)");
 results.push({year,documents:unique.length,index_sha256:report.source_sha256});
}
await writeFile(out+"/manifest.json",JSON.stringify({status:"PDF_URL_DISCOVERY_ONLY",results},null,2)+"\n");
