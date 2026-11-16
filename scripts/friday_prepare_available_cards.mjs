#!/usr/bin/env node
/**
 * Merge any retrieved Friday weekend card rows into a safe *provisional*
 * SQL staging CSV. Missing providers or records never terminate the report.
 * Usage: node scripts/friday_prepare_available_cards.mjs [CARD_DIRECTORY] [OUTPUT_DIRECTORY]
 *
 * No roster is claimed complete or officially verified by this function.
 */
import {existsSync, readdirSync, readFileSync, mkdirSync, writeFileSync} from "node:fs";
import {join} from "node:path";
const dir=process.argv[2]||"data/friday/weekend_cards";
const out=process.argv[3]||"reports/friday_operational";
mkdirSync(out,{recursive:true});
const columns=["date","venue","race_no","race_name","surface","distance_m","horse_no","horse_name","jockey_name","card_status","source_type","source_url","source_captured_utc"];
const allowedVenue=new Set(["札幌","函館","福島","新潟","東京","中山","中京","京都","阪神","小倉"]);
function csvParse(text){
 let s=text.replace(/^\uFEFF/,""),records=[],row=[],v="",quote=false;
 for(let i=0;i<s.length;i++){
  const c=s[i];
  if(quote){if(c==='"'&&s[i+1]==='"'){v+='"';i++;}else if(c==='"')quote=false;else v+=c;}
  else if(c==='"')quote=true;
  else if(c===','){row.push(v);v="";}
  else if(c==='\n'){row.push(v.replace(/\r$/,""));if(row.some(x=>x!==""))records.push(row);v="";row=[];}
  else v+=c;
 }
 if(quote)throw Error("Unclosed quote");
 if(v||row.length){row.push(v);records.push(row);}
 if(!records.length)return [];
 const headings=records.shift();
 return records.map((fields,i)=>{
  if(fields.length!==headings.length)throw Error("CSV data row "+(i+2)+" mismatched columns");
  return Object.fromEntries(headings.map((h,j)=>[h,fields[j]]));
 });
}
function csvEncode(rows){
 const cell=x=>'"'+String(x??"").replaceAll('"','""').replace(/\r?\n/g," ").replace(/\r/g," ")+'"';
 return columns.join(",")+"\n"+rows.map(r=>columns.map(k=>cell(r[k])).join(",")).join("\n")+(rows.length?"\n":"");
}
function nextSaturday(){
 const p=Object.fromEntries(new Intl.DateTimeFormat("en-US",{
  timeZone:"Asia/Tokyo",year:"numeric",month:"2-digit",day:"2-digit"
 }).formatToParts(new Date()).map(x=>[x.type,x.value]));
 const today=new Date(Date.UTC(+p.year,+p.month-1,+p.day));
 today.setUTCDate(today.getUTCDate()+(6-today.getUTCDay()+7)%7);
 return today.toISOString().slice(0,10);
}
const sat=process.env.FRIDAY_WEEKEND_SAT||nextSaturday();
if(!/^\d{4}-\d{2}-\d{2}$/.test(sat))throw Error("Invalid FRIDAY_WEEKEND_SAT");
const sunday=new Date(sat+"T00:00:00Z");sunday.setUTCDate(sunday.getUTCDate()+1);
const targetDays=new Set([sat,sunday.toISOString().slice(0,10)]);
const files=existsSync(dir)?readdirSync(dir).filter(x=>x.endsWith(".csv")).sort():[];
const warnings=[],seen=new Map(),details={files_scanned:files.length,rows_seen:0,rows_valid:0,duplicate:0,conflicts:0,ignored_other_dates:0,invalid:0};
for(const name of files){
 let rows;
 try{rows=csvParse(readFileSync(join(dir,name),"utf8"));}
 catch(e){warnings.push(name+" INVALID_CSV "+String(e));details.invalid++;continue;}
 for(const r of rows){
  details.rows_seen++;
  if(!targetDays.has(r.date)){details.ignored_other_dates++;continue;}
  const error=columns.slice(0,9).some(k=>!(k in r)) ||
   !allowedVenue.has(r.venue)||!(/^(?:[1-9]|1[0-2])$/).test(r.race_no)||
   !r.horse_name||r.horse_name.length>90||
   (r.horse_no!==""&&!/^(?:[1-9]|1[0-9]|2[0-9])$/.test(r.horse_no))||
   (r.surface!==""&&!["芝","ダート"].includes(r.surface))||
   (r.distance_m!==""&&!/^[0-9]{3,4}$/.test(r.distance_m));
  if(error){details.invalid++;warnings.push(name+" INVALID_ROW "+r.date+"/"+r.venue+"/"+r.race_no+"/"+(r.horse_name||"?"));continue;}
  const source_type=["SECONDARY_NETKEIBA","SECONDARY_OTHER","USER_PROVIDED"].includes(r.source_type)?r.source_type:"SOURCE_UNVERIFIED";
  if(source_type!=="USER_PROVIDED"){
    try{
      const u=new URL(r.source_url);
      if(u.protocol!=="https:"||!["race.sp.netkeiba.com","race.netkeiba.com","www.jra.go.jp","www.keibalab.jp","www.keibabook.co.jp"].includes(u.hostname))throw Error();
    }catch{details.invalid++;warnings.push(name+" INVALID_SOURCE_URL "+r.horse_name);continue;}
  }
  // A third-party or manual sheet is never upgraded to an official verified card.
  const candidate={...r,card_status:"PROVISIONAL",source_type,
    source_url:r.source_url||"",source_captured_utc:r.source_captured_utc||""};
  for(const k of columns) candidate[k]=String(candidate[k]??"").trim();
  const key=[candidate.date,candidate.venue,candidate.race_no,candidate.horse_name].join("|");
  const prior=seen.get(key);
  if(!prior){seen.set(key,candidate);details.rows_valid++;continue;}
  const same=prior.horse_no===candidate.horse_no&&prior.jockey_name===candidate.jockey_name;
  if(same){details.duplicate++;continue;}
  // Never silently choose between conflicting rider/horse number updates.
  prior.jockey_name="";
  prior.horse_no=(prior.horse_no===candidate.horse_no)?prior.horse_no:"";
  prior.card_status="CONFLICT_PROVISIONAL";
  prior.source_type="SOURCE_CONFLICT";
  warnings.push("CONFLICT "+key+": horse-number/rider source disagreement; identifiers left unverified");
  details.conflicts++;
 }
}
const sorted=[...seen.values()].sort((a,b)=>a.date.localeCompare(b.date)||a.venue.localeCompare(b.venue)||
 (+a.race_no)-(+b.race_no)||(+a.horse_no||99)-(+b.horse_no||99)||a.horse_name.localeCompare(b.horse_name));
writeFileSync(join(out,"cards_staging.csv"),csvEncode(sorted));
writeFileSync(join(out,"card_sources_status.json"),JSON.stringify({
  target_saturday:sat,target_sunday:[...targetDays][1],details,
  note:"PARTIAL_NOT_OFFICIAL_ROSTER_VERIFIED",warnings
},null,2)+"\n");
console.log("WEEKEND_CARDS_PREPARED "+JSON.stringify({sat,rows:sorted.length,files:files.length,invalid:details.invalid,conflicts:details.conflicts}));
