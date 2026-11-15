#!/usr/bin/env node
// Diagnose a saved authenticated JRA original race HTML, never fetched from blocked JRA endpoints.
import {readFileSync,existsSync,readdirSync} from "node:fs";
import {join,dirname} from "node:path";
import {createHash} from "node:crypto";
const root="/tmp/jra-shard";
const folders=readdirSync(root).filter(x=>x.startsWith("20"));
for(const folder of folders.slice(0,1)) {
 const manifest=JSON.parse(readFileSync(join(root,folder,"official_race_horse_ids.json"),"utf8"));
 const rec=manifest.records[0];
 const blob=readFileSync(join(root,folder,"raw",rec.source_sha256+".bin"));
 const sha=createHash("sha256").update(blob).digest("hex");
 if(sha!==rec.source_sha256)throw Error("source SHA mismatch");
 const text=new TextDecoder("shift_jis").decode(blob);
 console.log("RAW_RECORD",JSON.stringify({race:rec.race_id,source_url:rec.source_url,sha,horse_count:rec.horses?.length,charset:text.match(/charset.{0,35}/i)?.[0]}));
 const rows=[...text.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/gi)].slice(0,30);
 let recognized=0;
 for(const row of rows) {
   const columns=[...row[1].matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/gi)];
   if(columns.length<4)continue;
   const strip=s=>s.replace(/<[^>]*>/g,"").replace(/&nbsp;/g," ").replace(/&#(\d+);/g,(_,n)=>String.fromCodePoint(Number(n))).replace(/\s+/g," ").trim().slice(0,60);
   const number=strip(columns[2][1]);
   const href=[...columns[3][1].matchAll(/href\s*=\s*["']([^"']+)/gi)].map(x=>x[1]).filter(x=>x.includes("pw01dud"));
   if(/^\d{1,2}$/.test(number)) {
     console.log("RESULT_ROW",JSON.stringify({number,columns:columns.slice(0,10).map(x=>strip(x[1])),horse_href:href.slice(0,1),jockey_href:[...columns[6][1].matchAll(/href\s*=\s*[\"']([^\"']+)/gi)].map(x=>x[1]).slice(0,2)}));
     if(++recognized===5)break;
   }
 }
 console.log("HEADER_SAMPLE="+text.replace(/<script[\\s\\S]*?<\\/script>/gi,"").replace(/<[^>]*>/g," ").replace(/\\s+/g," ").slice(0,2200));
 console.log("PARSER_PROBE_MATCHED="+recognized);
 if(recognized<3)throw Error("saved race HTML structure not understood");
}
