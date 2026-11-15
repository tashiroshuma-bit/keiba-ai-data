#!/usr/bin/env node
/**
 * Restore JRA raw race HTML from previously captured GitHub Actions artifacts,
 * verifying original SHA and source-vs-manifest horse number/name/official ID.
 * Writes an append-only normalized CSV staging layer for sqlite3 .import.
 * Never fetches blocked JRA endpoints; never guesses official jockey IDs.
 */
import {readdirSync,readFileSync,mkdirSync,writeFileSync} from "node:fs";
import {join,dirname,relative} from "node:path";
import {createHash} from "node:crypto";
const root=process.argv[2]||"/tmp/jra-archive";
const out=process.argv[3]||"reports/friday_full_backfill/staging";
const max=Number(process.env.MAX_MANIFESTS||0);
mkdirSync(out,{recursive:true});
function walk(d) {
  const results=[];
  for(const ent of readdirSync(d,{withFileTypes:true})) {
    const p=join(d,ent.name);
    if(ent.isDirectory())results.push(...walk(p));
    else if(ent.isFile()&&ent.name==="official_race_horse_ids.json") results.push(p);
  }
  return results;
}
const manifests=walk(root).sort();
if(manifests.length===0)throw Error("NO_ARCHIVED_OFFICIAL_MANIFESTS");
if(max&&manifests.length>max)manifests.length=max;
const sha=b=>createHash("sha256").update(b).digest("hex");
const normalize=s=>String(s||"").normalize("NFKC").replace(/\s+/gu,"");
function decodeEntity(s) {
 return s.replace(/&#x([0-9a-f]+);/gi,(_,n)=>String.fromCodePoint(parseInt(n,16)))
  .replace(/&#(\d+);/g,(_,n)=>String.fromCodePoint(Number(n)))
  .replace(/&nbsp;|&ensp;|&emsp;/gi," ").replace(/&amp;/gi,"&")
  .replace(/&lt;/gi,"<").replace(/&gt;/gi,">").replace(/&quot;/gi,'"');
}
const plain=s=>decodeEntity(s.replace(/<[^>]*>/g,"")).replace(/\s+/gu," ").trim();
function parseHtml(blob) {
 const html=new TextDecoder("shift_jis").decode(blob);
 const res=[];
 for(const row of html.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/gi)) {
  const cells=[...row[1].matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/gi)].map(x=>x[1]);
  if(cells.length<7)continue;
  const number=plain(cells[2]);
  if(!/^\d{1,2}$/.test(number)||+number<1||+number>30)continue;
  const horses=[...cells[3].matchAll(/href\s*=\s*["']([^"']+)["']/gi)]
   .map(x=>decodeURIComponent(x[1])).map(x=>x.match(/pw01dud[0-9]*?(20[0-9]{8})\/[0-9a-f]{2}/i)?.[1])
   .filter(Boolean);
  if(horses.length!==1)continue;
  const order=plain(cells[0]);
  const jockeyText=plain(cells[6]);
  const jockeyLinks=[...cells[6].matchAll(/href\s*=\s*["']([^"']+)["']/gi)].map(x=>x[1]);
  res.push({horse_number:+number,horse_name:normalize(plain(cells[3])),horse_id:"jra:"+horses[0],
   finish_position:/^[0-9]{1,2}$/.test(order)?+order:null,
   status:order,jockey_name:jockeyText,jockey_link:jockeyLinks.length===1?jockeyLinks[0]:""});
 }
 return res;
}
const csv=(rows,keys)=>[keys.join(","),...rows.map(r=>keys.map(k=>'"'+String(r[k]??"").replace(/[\r\n]+/g," ").replace(/"/g,'""')+'"').join(","))].join("\n")+"\n";
const records=new Map(),issues=[],stat={manifests:manifests.length,manifest_races:0,observed_originals:0,source_verified_races:0,source_verified_runners:0,duplicate_races:0,duplicate_conflicts:0};
for(const file of manifests) {
 const manifest=JSON.parse(readFileSync(file,"utf8"));
 if(manifest.schema!=="jra-official-raw-results-horse-id-recovery-v1")throw Error("bad manifest schema "+file);
 for(const item of manifest.records||[]) {
  stat.manifest_races++;
  const id=String(item.race_id||""),url=String(item.source_url||"");
  const match=decodeURIComponent(url).match(/pw01sde(?:10|01)([0-9]{2})(20[0-9]{2})([0-9]{2})([0-9]{2})([0-9]{2})(20[0-9]{6})\/[0-9A-F]{2}/i);
  const computed=match?(match[2]+match[1]+match[3]+match[4]+match[5]):"";
  if(!match||computed!==id||!url.startsWith("https://www.jra.go.jp/JRADB/accessS.html?")) {
    issues.push({id,reason:"URL_RACE_ID_MISMATCH",file:relative(root,file)});continue;
  }
  const hash=String(item.source_sha256||"");
  if(!/^[0-9a-f]{64}$/.test(hash)) {issues.push({id,reason:"BAD_SOURCE_DIGEST"});continue;}
  const src=join(dirname(file),"raw",hash+".bin");
  let blob;
  try{blob=readFileSync(src)}catch{issues.push({id,reason:"MISSING_OFFICIAL_BYTES"});continue;}
  stat.observed_originals++;
  if(sha(blob)!==hash){issues.push({id,reason:"OFFICIAL_SOURCE_SHA_MISMATCH"});continue;}
  const runners=parseHtml(blob);
  const claimed=new Map((item.horses||[]).map(h=>[+h.horse_number,{horse_name:normalize(h.horse_name),horse_id:h.horse_id}]));
  const observed=new Map(runners.map(h=>[h.horse_number,h]));
  if(runners.length<3||new Set(runners.map(x=>x.horse_id)).size!==runners.length||
     observed.size!==claimed.size||
     [...claimed].some(([n,h])=>!observed.has(n)||observed.get(n).horse_id!==h.horse_id||observed.get(n).horse_name!==h.horse_name)) {
    issues.push({id,reason:"SOURCE_MANIFEST_RUNNER_ID_OR_NAME_MISMATCH",claimed:claimed.size,observed:observed.size});continue;
  }
  const calendar=match[6],race_date=calendar.slice(0,4)+"-"+calendar.slice(4,6)+"-"+calendar.slice(6,8);
  const row={race_id:id,race_date,year:+match[2],venue_code:match[1],meeting:+match[3],meeting_day:+match[4],race_number:+match[5],
    source_url:url,source_sha256:hash,observed_at:item.observed_at,horse_count:runners.length,
    source_scope:"JRA_OFFICIAL_ORIGINAL_SHA_VERIFIED",runners};
  if(records.has(id)) {
    stat.duplicate_races++;
    const previous=records.get(id),sig=xs=>JSON.stringify(xs.map(h=>[h.horse_number,h.horse_name,h.horse_id,h.finish_position,h.jockey_name]).sort((a,b)=>a[0]-b[0]));
    if(sig(previous.runners)!==sig(row.runners)) {
      stat.duplicate_conflicts++;issues.push({id,reason:"DUPLICATE_OFFICIAL_PAGE_DISAGREEMENT"});records.delete(id);
    }
    continue;
  }
  records.set(id,row);stat.source_verified_races++;stat.source_verified_runners+=runners.length;
 }
}
const races=[...records.values()].sort((a,b)=>a.race_id.localeCompare(b.race_id));
const runnerRows=races.flatMap(r=>r.runners.map(h=>({race_id:r.race_id,source_sha256:r.source_sha256,...h})));
const byYear={};
for(const r of races){const x=byYear[r.year]||(byYear[r.year]={races:0,runners:0,missing_jockey_link:0,missing_finish:0});x.races++;x.runners+=r.runners.length;x.missing_jockey_link+=r.runners.filter(h=>!h.jockey_link).length;x.missing_finish+=r.runners.filter(h=>h.finish_position===null).length;}
writeFileSync(out+"/races.csv",csv(races,["race_id","race_date","year","venue_code","meeting","meeting_day","race_number","source_url","source_sha256","observed_at","horse_count","source_scope"]));
writeFileSync(out+"/runners.csv",csv(runnerRows,["race_id","horse_number","horse_name","horse_id","finish_position","status","jockey_name","jockey_link","source_sha256"]));
writeFileSync(out+"/quarantine.json",JSON.stringify(issues,null,2)+"\n");
const summary={...stat,source_verified_races:races.length,source_verified_runners:runnerRows.length,year_counts:byYear,quarantined:issues.length,
 status:"JRA_ORIGINAL_IDENTITY_AND_RESULT_ROWS_VERIFIED_METRICS_NOT_YET_FULLY_CERTIFIED"};
writeFileSync(out+"/summary.json",JSON.stringify(summary,null,2)+"\n");
console.log("JRA_ARCHIVE_REPLAY_SUMMARY="+JSON.stringify(summary));
if(!races.length)process.exitCode=2;
