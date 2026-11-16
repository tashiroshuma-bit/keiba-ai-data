#!/usr/bin/env node
/**
 * Best-effort SECONDARY public Sat/Sun racecard retrieval (netkeiba).
 * No Python. Failure/403/HTML changes never prevent historical delivery.
 * Output is explicitly PROVISIONAL, not an independently certified JRA card.
 */
import {mkdirSync,writeFileSync} from "node:fs";
const out="data/friday/weekend_cards";
mkdirSync(out,{recursive:true});
function tokyoDate(){
 const parts=Object.fromEntries(new Intl.DateTimeFormat("en-US",{timeZone:"Asia/Tokyo",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date()).map(p=>[p.type,p.value]));
 const d=new Date(Date.UTC(Number(parts.year),Number(parts.month)-1,Number(parts.day)));
 d.setUTCDate(d.getUTCDate()+(6-d.getUTCDay()+7)%7);
 return d.toISOString().slice(0,10);
}
const sat=process.env.FRIDAY_WEEKEND_SAT||tokyoDate();
const dates=[sat, new Date(Date.parse(sat+"T00:00:00Z")+86400000).toISOString().slice(0,10)];
const racesByVenue={"01":"札幌","02":"函館","03":"福島","04":"新潟","05":"東京","06":"中山","07":"中京","08":"京都","09":"阪神","10":"小倉"};
const columns=["date","venue","race_no","race_name","surface","distance_m","horse_no","horse_name","jockey_name","card_status","source_type","source_url","source_captured_utc"];
function serialize(rows){
 const enc=x=>'"'+String(x??"").replaceAll('"','""').replace(/\r?\n/g," ")+'"';
 return columns.join(",")+"\n"+rows.map(r=>columns.map(k=>enc(r[k])).join(",")).join("\n")+(rows.length?"\n":"");
}
const clean=s=>String(s??"").replace(/<script\b[\s\S]*?<\/script>/gi,"")
 .replace(/<[^>]*>/g," ").replace(/&nbsp;|&#160;/gi," ")
 .replace(/&amp;/gi,"&").replace(/&#([0-9]+);/g,(_,n)=>String.fromCodePoint(Number(n)))
 .replace(/\s+/g," ").trim();
async function get(url){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),7000);
 try{
  const r=await fetch(url,{signal:controller.signal,headers:{"user-agent":"Mozilla/5.0 (compatible; JRA-History-Reader/1.0)","accept":"text/html,application/xhtml+xml"},redirect:"follow"});
  if(!r.ok)throw Error("HTTP "+r.status);
  if(new URL(r.url).hostname!=="race.sp.netkeiba.com")throw Error("unexpected redirect origin");
  const raw=await r.arrayBuffer();
  if(raw.byteLength<400||raw.byteLength>3_000_000)throw Error("invalid HTML size");
  return new TextDecoder("utf-8",{fatal:false}).decode(raw);
 }finally{clearTimeout(timer);}
}
const audit={retrieved_utc:new Date().toISOString(),weekend:dates,days:[],race_pages_attempted:0,race_pages_parsed:0,usable_entries:0,warnings:[],
 note:"SECONDARY_PROVISIONAL_ROSTER_NOT_JRA_OFFICIALLY_VERIFIED"};
for(const date of dates){
 const compact=date.replaceAll("-","");
 const listUrl="https://race.sp.netkeiba.com/top/race_list.html?kaisai_date="+compact;
 let page;
 try{page=await get(listUrl);}catch(e){audit.warnings.push("LIST "+date+" "+String(e));audit.days.push({date,status:"LIST_UNAVAILABLE",races:0,horses:0});continue;}
 const matches=[...page.matchAll(/(?:race_id=|\/race\/)(20[0-9]{10})/g)].map(x=>x[1]);
 const ids=[...new Set(matches)].filter(id=>Number(id.slice(0,4))===Number(date.slice(0,4))
    &&racesByVenue[id.slice(4,6)]&&Number(id.slice(-2))>=1&&Number(id.slice(-2))<=12).slice(0,42);
 if(!ids.length){audit.warnings.push("LIST "+date+" no supported 12-digit race IDs");audit.days.push({date,status:"RACE_IDS_UNAVAILABLE",races:0,horses:0});continue;}
 const rows=[];let raceCount=0;
 for(const raceId of ids){
  audit.race_pages_attempted++;
  const url="https://race.sp.netkeiba.com/race/shutuba.html?race_id="+raceId;
  let html;
  try{html=await get(url);}catch(e){audit.warnings.push("RACE "+raceId+" "+String(e));continue;}
  const title=clean(html.match(/<h1[^>]*class=["'][^"']*(?:RaceName|Race_Name)[^"']*["'][^>]*>([\s\S]*?)<\/h1>/i)?.[1]||"");
  if(title.includes("障害"))continue;
  const raceNo=Number(raceId.slice(-2));
  const venue=racesByVenue[raceId.slice(4,6)];
  const conditionHtml=clean(html.slice(0,Math.min(html.length,100000)));
  const condition=conditionHtml.match(/(芝|ダート)\s*([0-9]{3,4})\s*m/i);
  const surface=condition?.[1]||"",distance_m=condition?.[2]||"";
  let found=0;
  for(const match of html.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/gi)){
   const row=match[1];
   const horseAnchor=row.match(/<a\b[^>]*href=["'][^"']*\/horse\/(?:[a-zA-Z0-9_/]+)?["'][^>]*>([\s\S]*?)<\/a>/i);
   if(!horseAnchor)continue;
   const horse_name=clean(horseAnchor[1]).normalize("NFKC");
   if(!horse_name||horse_name.length>70)continue;
   const td=row.match(/<td\b[^>]*class=["'][^"']*(?:Umaban|HorseNum|Horse_Number)[^"']*["'][^>]*>([\s\S]*?)<\/td>/i);
   const horse_no=clean(td?.[1]||"").match(/^\d{1,2}$/)?.[0]||"";
   const jockeyAnchor=row.match(/<a\b[^>]*href=["'][^"']*\/jockey\/[a-zA-Z0-9_/]*["'][^>]*>([\s\S]*?)<\/a>/i);
   const jockey_name=clean(jockeyAnchor?.[1]||"").normalize("NFKC");
   rows.push({date,venue,race_no:String(raceNo),race_name:title||"レース名未確認",
    surface,distance_m,horse_no,horse_name,jockey_name,card_status:"PROVISIONAL",
    source_type:"SECONDARY_NETKEIBA",source_url:url,source_captured_utc:new Date().toISOString()});
   found++;
  }
  if(found>0){raceCount++;audit.race_pages_parsed++;}
  else audit.warnings.push("RACE "+raceId+" unparseable: 0 identifiable horses");
 }
 if(rows.length)writeFileSync(out+"/netkeiba_"+date+".csv",serialize(rows));
 audit.usable_entries+=rows.length;
 audit.days.push({date,status:rows.length?"PARTIAL_ROWS_COLLECTED":"NO_USABLE_HORSES",races:raceCount,horses:rows.length});
}
writeFileSync("reports/friday_card_acquisition.json",JSON.stringify(audit,null,2)+"\n");
console.log("SECONDARY_WEEKEND_FETCH "+JSON.stringify({days:audit.days,race_pages:audit.race_pages_attempted,usable_entries:audit.usable_entries,warnings:audit.warnings.length}));
console.log("No all-race guarantee; runner used fallback safely if source unavailable.");
