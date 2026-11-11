"""Catch up JRA verified-result race days with uncovered horse IDs only.

Each source HTML is fetched with a min delay, SHA-addressed and immutable.
This script never modifies or imputes the canonical horse ID database.
"""
import argparse
import json
from pathlib import Path
from scripts.jra_official_race_bulk_id_crawler import run,race_id_from_url,race_calendar_date

def collect(seed_path,out_dir,shard,shards,limit=65,delay=1.5):
    data=json.loads(Path(seed_path).read_bytes())
    if data.get("schema")!="jra-missing-null-horse-id-days-v1":
        raise ValueError("missing-day seed schema invalid")
    if not 1<=shards<=128 or not 0<=shard<shards:
        raise ValueError("invalid shard index")
    if delay<1.0 or not 1<=limit<=500:raise ValueError("unbounded fetch")
    days=data["target_days"]
    dates=[x["race_date"] for x in days]
    if len(dates)!=len(set(dates)):raise ValueError("duplicate dates")
    root=Path(out_dir)
    if root.exists() and any(root.iterdir()):raise FileExistsError("output immutable")
    root.mkdir(parents=True,exist_ok=True)
    records=[];failures=[]
    for i,row in enumerate(days):
        if i%shards!=shard:continue
        date=row["race_date"];url=row["seed_url"]
        if race_calendar_date(url)!=date or race_id_from_url(url)!=row["race_id"]:
            raise ValueError("date or official race ID seed not authentic")
        try:
            result=run([url],root/date,max_pages=limit,delay=delay,target_date=date)
            records.append({"date":date,"original_missing_rows":row["missing_horse_id_rows"],**result})
            if result["success"]==0 or result["failed"]:
                failures.append({"date":date,"reason":"source returned zero pages or had failures",**result})
        except Exception as ex:
            failures.append({"date":date,"reason":type(ex).__name__+":"+str(ex)[:300]})
    summary={"schema":"jra-missing-day-primary-id-capture-v1",
        "source_seed_sha256":__import__("hashlib").sha256(Path(seed_path).read_bytes()).hexdigest(),
        "shard":shard,"shards":shards,"selected_days":len(records)+len([a for a in failures if "success" not in a]),
        "successful_date_batches":len(records),"pages_downloaded":sum(x["success"] for x in records),
        "official_horse_links":sum(x["horse_rows"] for x in records),
        "failures":failures,"records":records,"canonical_not_modified":True}
    (root/"batch_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    return summary

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--seed-file",required=True)
    p.add_argument("--output-dir",required=True)
    p.add_argument("--shard",type=int,required=True)
    p.add_argument("--shards",type=int,required=True)
    p.add_argument("--limit",type=int,default=65)
    p.add_argument("--delay",type=float,default=1.5)
    a=p.parse_args()
    result=collect(a.seed_file,a.output_dir,a.shard,a.shards,a.limit,a.delay)
    print(json.dumps({"shard":a.shard,"days":result["selected_days"],"pages":result["pages_downloaded"],
                      "source_rows":result["official_horse_links"],"failures":result["failures"]},ensure_ascii=False))
if __name__=="__main__":main()
