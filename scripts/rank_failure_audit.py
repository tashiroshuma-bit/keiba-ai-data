"""Profile a fixed rank candidate's errors without choosing a new race subset."""
import argparse
import collections
import gzip
import json
from pathlib import Path
import sqlite3


def audit(db,predictions):
    records=json.loads(gzip.decompress(Path(predictions).read_bytes()))
    with sqlite3.connect(Path(db).resolve().as_uri()+'?mode=ro',uri=True) as c:
        ids={(rid,str(num)):hid for rid,num,hid in c.execute('select race_id,horse_number,horse_id from annual_report_runners')}
    groups=collections.defaultdict(list)
    for r in records:
        p=r['candidate'];numbers=r['horse_numbers'];n=len(numbers)
        missing=sum(not ids.get((r['race_id'],num)) for num in numbers)/n
        linked='all_linked' if missing==0 else 'up_to_half_unlinked' if missing<=.5 else 'more_than_half_unlinked'
        field='3_to_8' if n<=8 else '9_to_12' if n<=12 else '13_or_more'
        confidence=max(x[0] for x in p['marginal_probabilities'])
        band='below_40pct' if confidence<.4 else '40_to_60pct' if confidence<.6 else '60_to_80pct' if confidence<.8 else '80pct_or_more'
        for dimension,key in (('identity',linked),('field_size',field),('winner_confidence',band)):
            groups[r['date'][:4],dimension,key].append(p)
    result=[]
    totals=collections.Counter(r['date'][:4] for r in records)
    for (year,dimension,segment),rows in sorted(groups.items()):
        n=len(rows)
        result.append(dict(year=year,dimension=dimension,segment=segment,races=n,coverage=n/totals[year],
            **{k:sum(v[k] for v in rows)/n for k in ('winner_hit','top3_all_hit','ordered_all_hit')}))
    return dict(scope='fixed previous rank candidate; diagnostic only, no subset selected for target claims',segments=result)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('db','predictions','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();value=audit(a.db,a.predictions)
    Path(a.output).write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value))
