#!/usr/bin/env node
/** Mobile-first Markdown renderer for source-backed JRA race histories. No Python. */
import {readFileSync,writeFileSync,mkdirSync,existsSync} from "node:fs";
import {join} from "node:path";
const [,,mode,input,output]=process.argv;
if(!["preview","partial","status"].includes(mode))throw Error("Use preview|partial INPUT.csv OUTPUT_DIR or status REPORT_DIR");
function csv(path){
 const s=readFileSync(path,"utf8").replace(/^\uFEFF/,"");const rec=[];let row=[],v="",q=false;
 for(let i=0;i<s.length;i++){
  const c=s[i];
  if(q){if(c==='"'&&s[i+1]==='"'){v+='"';i++;}else if(c==='"')q=false;else v+=c;}
  else if(c==='"')q=true;
  else if(c===","){row.push(v);v="";}
  else if(c==="\n"){row.push(v.replace(/\r$/,""));if(row.some(x=>x!==""))rec.push(row);row=[];v="";}
  else v+=c;
 }
 if(q)throw Error("Unclosed CSV quote: "+path);
 if(v||row.length){row.push(v);rec.push(row);}
 if(rec.length<2)throw Error("CSV needs header and records: "+path);
 const keys=rec.shift();
 return rec.map((values,i)=>{
  if(values.length!==keys.length)throw Error("CSV row "+(i+2)+" inconsistent columns");
  return Object.fromEntries(keys.map((k,n)=>[k,values[n]]));
 });
}
const esc=x=>String(x??"").replaceAll("|","\\|").replaceAll("\n"," ").replaceAll("<","&lt;").replaceAll(">","&gt;");
function uint(x,label){
 if(x===""||x===undefined||x===null)return null;
 if(!/^\d+$/.test(String(x)))throw Error("Bad unsigned value "+label+"="+x);
 return Number(x);
}
function rate(n,d,label){
 if(d===null||n===null)return "未照合";
 if(d===0)return "－";
 if(n>d)throw Error(label+" numerator > denominator");
 return "**"+(100*n/d).toFixed(1).replace(/\.0$/,"")+"%** ("+n+"/"+d+")";
}
function rates(row,prefix){
 const d=uint(row[prefix+"_starts"],prefix+"_starts");
 return {win:rate(uint(row[prefix+"_wins"],prefix+"_wins"),d,prefix),
         top3:rate(uint(row[prefix+"_top3"],prefix+"_top3"),d,prefix)};
}
function racePage(rows,partial=false){
 const a=rows[0];
 const condition=[a.surface,a.distance_m?a.distance_m+"m":""].filter(Boolean).map(esc).join(" ");
 const md=[
  "# "+esc(a.date)+" "+esc(a.venue)+esc(a.race_no)+"R｜"+esc(a.race_name),
  "",
  "**"+condition+"**　｜　"+(partial?"取得できた出走情報（未確定・一部のみの可能性あり）":"登録段階の表示例（確定出馬表ではありません）")+"　｜　掲載"+rows.length+"頭",
  "",
  "> 対象は2023～2025年のJRA平地実績。過去勝率と今回の勝率予測は異なります。",
  "",
  "### ① 馬ごとの実績",
  "",
  "| 馬番 | 馬名 / 想定騎手 | 1着率 | 3着以内率 |",
  "|:--:|:--|--:|--:|"
 ];
 for(const r of rows){
  const m=rates(r,"horse");
  md.push("| "+esc(r.horse_no||"－")+" | **"+esc(r.horse_name)+"** / "+esc(r.jockey_name||"騎手未定")+" | "+m.win+" | "+m.top3+" |");
 }
 md.push("","### ② 騎手・コンビ・コース別","","| 馬名 | 騎手3着内 | コンビ3着内 | 同コース3着内 |","|:--|--:|--:|--:|");
 for(const r of rows){
  const j=rates(r,"jockey"),p=rates(r,"pair");
  md.push("| "+esc(r.horse_name)+" | "+j.top3+" | "+p.top3+" | "+rate(uint(r.condition_top3,"condition_top3"),uint(r.condition_starts,"condition_starts"),"condition")+" |");
 }
 md.push("",
  "**記号の意味**：－＝同条件で出走記録なし（0戦）、未照合＝IDまたは履歴が確認できない、0% (0/5)＝5戦して3着以内0回。",
  "",
  "※同コースとは競馬場・芝ダート・距離が一致するレース。馬場状態、内外回り、相手関係は別途確認します。",
  "",
  partial ? "**出走情報の出典種別**："+[...new Set(rows.map(r=>esc(r.source_type||"SOURCE_UNVERIFIED")))].join("、")+"。取得分のみのため全頭・騎手の確定は保証されません。" : "",
  "");
 return md.join("\n");
}
if(mode==="preview"||mode==="partial"){
 if(!input||!output)throw Error("preview INPUT.csv OUTPUT_DIR required");
 const rows=csv(input);
 for(const r of rows)for(const k of ["date","venue","race_no","race_name","horse_name","card_status","horse_starts","horse_wins","horse_top3"])if(!(k in r))throw Error("Missing field "+k);
 if(mode==="preview"&&rows.some(r=>r.card_status!=="PROVISIONAL"))throw Error("Only explicitly provisional cards may enter preview");
 mkdirSync(output,{recursive:true});
 const grouped=new Map();
 for(const r of rows){const key=[r.date,r.venue,r.race_no].join("|");if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(r);}
 const links=[];
 for(const [key,group] of [...grouped.entries()].sort((a,b)=>a[0].localeCompare(b[0]))){
  group.sort((a,b)=>Number(a.horse_no||100)-Number(b.horse_no||100)||a.horse_name.localeCompare(b.horse_name));
  const r=group[0],file=r.date+"_"+r.venue+"_"+r.race_no+"R.md";
  writeFileSync(join(output,file),racePage(group,mode==="partial"));
  links.push("| "+esc(r.date)+" | "+esc(r.venue)+esc(r.race_no)+"R | ["+esc(r.race_name)+"（"+group.length+"頭）](./"+encodeURIComponent(file)+") | "+(mode==="partial"?"一部取得・未確定":"登録・想定")+" |");
 }
 writeFileSync(join(output,"INDEX.md"),[
  (mode==="partial"?"# 金曜21:00 JRA週末実績｜取得できたレースから公開":"# 金曜21:00 JRA週末実績（レイアウト例）"),"",
  (mode==="partial"?"**部分レポートです。記載のないレースや馬が存在する可能性があり、公式の全頭照合は未完了です。**":"**登録段階の表示テストです。出走馬・騎手は確定していません。**"),
  "実績の集計対象は2023～2025年。2026年の部分保存データ、予想オッズ、予測確率は混ぜていません。","",
  "| 日付 | 競馬場 | レース | 状態 |","|:--|:--|:--|:--|",...links,"",
  "各レースの詳細で、馬の実績と騎手・人馬コンビの実績を別表に分けています。","",
  "検証元：[JRA履歴SQL実行記録](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/43783928140)",""
 ].join("\n"));
 console.log((mode==="partial"?"MOBILE_PARTIAL_GENERATED":"MOBILE_PREVIEW_GENERATED")+" races="+grouped.size+" entries="+rows.length);
}else{
 if(!input)throw Error("status REPORT_DIR required");
 mkdirSync(input,{recursive:true});
 const status=existsSync(join(input,"status.txt"))?readFileSync(join(input,"status.txt"),"utf8").trim():"集計状態未確認";
 const annual=existsSync(join(input,"scheduled_coverage.csv"))?csv(join(input,"scheduled_coverage.csv")):[];
 const yr=annual.map(r=>"| "+esc(r.year)+" | "+esc(r.result_races)+" | "+esc(r.officially_cancelled)+" | "+esc(r.scheduled_races)+" |");
 writeFileSync(join(input,"INDEX.md"),[
  "# 金曜21:00 JRA週末実績レポート","",
  "## 週末レース別：公式出馬表の照合待ち","",
  "**過去3年の履歴DBと集計は利用可能です。** ただし、次の土日の全出走馬・騎手を公式原本で確認できない限り、馬ごとの週末レポートは確定表示しません。","",
  "> "+esc(status),"",
  "### 過去3年間の収録状況","",
  "| 年 | レース結果あり | 競走取りやめ | 予定レース |",
  "|:--|--:|--:|--:|",...yr,"",
  "### 監査用データ","",
  "- 馬・騎手・人馬コンビ：official_2023_2025_actor_condition_stats.csv",
  "- 各馬の直近5走：official_2023_2025_recent5.csv","",
  "※公式出馬表の全頭照合に成功したレースから、上記の読みやすいレース別表に接続します。","",
  "[正本DBの保存記録](https://github.com/tashiroshuma-bit/keiba-ai-data/blob/data/friday-three-year-history/snapshots/archived_official_history.status)","",""
 ].join("\n"));
 console.log("MOBILE_STATUS_GENERATED racecards=NOT_READY");
}
