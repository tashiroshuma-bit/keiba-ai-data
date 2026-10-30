"""Export the existing learned rider feature from proven observed history."""
import argparse,datetime as dt,hashlib,json,sqlite3,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'keiba_v48'))
from enriched_features import load_observed_enriched
from features import HistoryIndex,timestamp

def export(db_path,asof):
    with open(db_path,'rb') as handle:digest=hashlib.file_digest(handle,'sha256').hexdigest()
    if digest!='5a7dcd864286ccb60a43dd644a0fbe050ea25425e7e39effa7fa70fdc3128ebc':
        raise ValueError('canonical DB version 10 required')
    history=load_observed_enriched(db_path,asof)
    index=HistoryIndex(history,allow_missing_jockey=True)
    statistics={}
    for jid in index.groups['jockey']:
        value,samples=index.jockey_form(jid,'future_not_in_history',asof+dt.timedelta(days=1),asof)
        statistics[jid]={'value':value,'samples':samples}
    with sqlite3.connect('file:'+str(Path(db_path).resolve())+'?mode=ro',uri=True) as c:
        catalog=c.execute('select distinct jockey_id,jockey_name from official_identity_evidence where jockey_id is not null').fetchall()
    return {'schema':'observed-jockey-feature-snapshot-v1','database_sha256':digest,'database_version':10,
            'asof':asof.isoformat(),'history_rows':len(history),'latest_race_date':max(r['race_date'] for r in history),
            'latest_result_available_at':max(timestamp(r['result_available_at']) for r in history).isoformat(),
            'definition':'(prior valid-finish top-three count + 5) / (prior valid-finish starts + 20); observed source and identity proof required',
            'statistics':statistics,'direct_identity_catalog':catalog}

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('db','asof','output'):p.add_argument('--'+key,required=True)
    a=p.parse_args();dest=Path(a.output)
    if dest.exists():raise ValueError('immutable output exists')
    result=export(a.db,timestamp(a.asof));dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('statistics','direct_identity_catalog')},ensure_ascii=False))
