#!/usr/bin/env node
// Inventory Git-tracked data artifacts. Excludes source code and synthetic fixtures.
import { execFileSync } from "node:child_process";
import { statSync, mkdirSync, writeFileSync } from "node:fs";
const all=execFileSync("git",["ls-files","-z"],{maxBuffer:30*1024*1024}).toString("utf8").split("\0").filter(Boolean);
const data=all.filter(p=>/\.(sqlite|db|csv|tsv|parquet|arrow|jsonl|jsonl\.gz|json\.gz|csv\.gz|zip|zst|tar\.gz)$/i.test(p)).map(p=>{let size=0;try{size=statSync(p).size}catch{}return {path:p,bytes:size};}).sort((a,b)=>b.bytes-a.bytes);
mkdirSync("reports/friday_full_backfill/local",{recursive:true});
writeFileSync("reports/friday_full_backfill/local/git_data_assets.json",JSON.stringify({scope:"ONLY_GIT_TRACKED_DATA_NOT_LIBRARY",files:data},null,2)+"\n");
const grouped={};
for(const a of data){let ext=a.path.split(".").pop().toLowerCase(); if(!grouped[ext])grouped[ext]={files:0,bytes:0};grouped[ext].files++;grouped[ext].bytes+=a.bytes;}
console.log("TOTAL_FILES="+data.length,"CATEGORIES="+JSON.stringify(grouped));
for(const x of data.slice(0,80))console.log("DATA_ASSET "+x.bytes+" "+x.path);
