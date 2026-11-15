#!/usr/bin/env node
// Inspect saved official JRA HTML race header metadata without network or Python.
import {readdirSync,readFileSync} from "node:fs";
import {join} from "node:path";
const root="/tmp/jra-shard";
let n=0;
for (const dir of readdirSync(root)) {
 const path=join(root,dir,"official_race_horse_ids.json");
 let manifest;
 try{manifest=JSON.parse(readFileSync(path,"utf8"))}catch{continue}
 for(const record of manifest.records.slice(0,4)) {
  const html=new TextDecoder("shift_jis").decode(readFileSync(join(root,dir,"raw",record.source_sha256+".bin")));
  const clean=html.replace(/<script\b[\s\S]*?<\/script>/gi," ").replace(/<style\b[\s\S]*?<\/style>/gi," ").replace(/<[^>]*>/g," ").replace(/\s+/g," ");
  console.log("META_RACE="+record.race_id+" CLEAN_LENGTH="+clean.length);
  for (const word of ["ダート","芝","馬場状態","天候","発走","距離","障害"]) {
   let k=0;
   for(const m of clean.matchAll(new RegExp(word,"g"))) {
     console.log("META_"+word+" "+clean.slice(Math.max(0,m.index-75),m.index+115));
     if(++k>=3)break;
   }
  }
  const row=[...html.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/gi)]
   .map(m=>[...m[1].matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/gi)].map(x=>x[1]))
   .find(cols=>cols.length>=7 && /pw01dud/i.test(cols[3]));
  if(row)console.log("JOCKEY_CELL_HTML="+row[6].slice(0,500));
  if(++n>=2)process.exit(0);
 }
}
