"""Full flat-weekend rider overlay, keeping original freezes immutable."""
import argparse,base64,datetime as dt,hashlib,json,math,re,sys,unicodedata,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'keiba_v48'),str(ROOT/'scripts')]
from ranking_model import RankModel,NAMES
from jockey_feature_overlay import overlay
from jockey_overlay_ticket_math import calculate_model

def digest(path):
    with open(path,'rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()

def norm(value):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',value)).lstrip('▲△☆★◇')

def card_rows(snapshot):
    """Exclude headers and excluded-horse footers; preserve cancelled rows."""
    return [row for row in snapshot['rows'] if any('uma' in c['class'] for c in row['cells'])
            and any('accessU' in a['href'] for a in row['links'])]

def official_rider(row):
    link=next((a for a in row['links'] if a.get('onclick') and 'accessK' in a['onclick']),None)
    if link:
        match=re.search(r'sw04kmk01(\d{4})/',link['onclick'])
        if not match:raise ValueError('unknown official rider code format')
        return link['text'],link['onclick'],match[1]
    displayed=re.findall(r'([^\s()]+)\s*\((\d{2}(?:\.\d)?)\)',row['text'])
    if len(displayed)!=1:raise ValueError('unlinked rider name unavailable')
    return displayed[0][0],None,None

def decode_odds(snapshot):
    if snapshot.get('error'):return {'status':'unavailable','reason':snapshot['error']}
    text=snapshot.get('text','')
    if not text.startswith('odds_callback(') or not text.endswith(')'):
        return {'status':'unavailable','reason':'unexpected response framing'}
    response=json.loads(text[len('odds_callback('):-1])
    status=response.get('status')
    result={'status':status,'source_url':snapshot['url'],'source_sha256':snapshot['sha256'],'observed_at':snapshot['at']}
    if status not in ('middle','yoso'):
        result['reason']='current/predicted quotes unavailable; final quotes not used'
        return result
    body=response.get('data')
    if not body:return {**result,'reason':'empty quote data'}
    data=json.loads(zlib.decompress(base64.b64decode(body)))
    result.update(data)
    return result

def recalculate(baselines,evidence,rider_snapshot,model):
    if rider_snapshot.get('schema')!='observed-jockey-feature-snapshot-v1':raise ValueError('verified rider snapshot required')
    statistics=rider_snapshot['statistics'];catalog=rider_snapshot['direct_identity_catalog']
    output={'schema':'weekend-rider-overlay-v1','status':'research_only_not_calibrated_not_promoted',
            'created_at':dt.datetime.now(dt.timezone.utc).isoformat(),'rider_history_asof':rider_snapshot['asof'],
            'history_rows':rider_snapshot['history_rows'],'history_latest_race':rider_snapshot['latest_race_date'],
            'changed_features':['jockey_form','jockey_identity_missing'],'remaining_career_proxy':True,
            'race_failures':[],'races':[]}
    for observation in evidence['races']:
        date,label=observation['date'],observation['race']
        try:
            base=next(r for r in baselines[date]['races'] if r['race']==label)
            if base['surface']=='obstacle':raise ValueError('obstacle excluded')
            snapshot=observation['jra']
            if 'error' in snapshot:raise ValueError('official card missing: '+snapshot['error'])
            off=dt.datetime.fromisoformat(base['off_at']);asof=dt.datetime.fromisoformat(snapshot['at'])
            if asof>=off-dt.timedelta(minutes=5):raise ValueError('not a pre-off snapshot')
            if dt.datetime.fromisoformat(rider_snapshot['asof'])>asof:raise ValueError('rider data postdates card')
            rows=card_rows(snapshot)
            rowmap={norm(next(a['text'] for a in row['links'] if 'accessU' in a['href'])):row for row in rows}
            if len(rowmap)!=len(rows):raise ValueError('duplicate official runner name')
            if set(rowmap)!={norm(h['name']) for h in base['runners']}:raise ValueError('official runner set changed')
            active_old=[h for h in base['runners'] if not h.get('withdrawn')]
            oldmap={h['name']:h['p1'] for h in base['models']['A']['horses']}
            def feature(horse):
                values=model.mean.tolist();starts=horse['starts']
                changes={'ability':(horse['wins']+1)/(starts+4),'recent_quality':(horse['wins']+horse['seconds']+horse['thirds']+1)/(starts+2),'history_log':math.log1p(starts)/5,'horse_identity_missing':1,'jockey_identity_missing':1,'age_missing':1}
                for key,value in changes.items():values[NAMES.index(key)]=value
                return {'values':values,'group':base['track']+'/'+base['surface'],'cutoff_timestamp':snapshot['at']}
            original_features=[feature(h) for h in active_old]
            original_probabilities,_=model.predict(original_features)
            if max(abs(float(original_probabilities[i,0])-oldmap[h['name']]) for i,h in enumerate(active_old))>1e-10:
                raise ValueError('original A prediction not reproduced')
            horses=[];frame=None;excluded=[]
            for row in rows:
                name=next(a['text'] for a in row['links'] if 'accessU' in a['href'])
                horse=dict(next(h for h in base['runners'] if norm(h['name'])==norm(name)))
                cell=next(c for c in row['cells'] if 'uban' in c['class'])
                explicit=next((c['text'] for c in row['cells'] if 'wban' in c['class']),None)
                if explicit and explicit.isdigit():frame=int(explicit)
                cancelled='取消' in row['text'] or '除外' in cell['text']
                if cancelled:
                    excluded.append({'name':horse['name'],'number':horse['number'],'reason':'official_current_withdrawal'})
                    continue
                number=int(cell['text']) if cell['text'].isdigit() else None
                if horse['number'] is not None and number!=horse['number']:raise ValueError('published horse number changed')
                horse.update(number=number,frame=frame if number is not None else None)
                rider_name,rider_action,rider_suffix=official_rider(row)
                if rider_suffix:
                    candidates={jid for jid,jname in catalog if jid.endswith(rider_suffix) and norm(jname)==norm(rider_name)}
                else:
                    old_name=horse.get('jockey')
                    horse['jockey']=rider_name
                    if old_name!=horse['jockey']:
                        horse['jockey_parser_repair']={'old':old_name,'observed':horse['jockey'],'basis':'official displayed name immediately before assigned weight; trainer anchor not rider'}
                    candidates=set()
                if len(candidates)>1:raise ValueError('ambiguous rider identity')
                horse.update(jockey=rider_name,jockey_id=next(iter(candidates),None),jockey_source_action=rider_action)
                horse['jockey_identity_basis']='official_mobile_code_suffix_and_name_match_direct_DB_evidence' if candidates else 'unmatched_official_identity_no_history_join'
                horse['jockey_form']=statistics.get(horse['jockey_id'],{}).get('value',.25)
                horse['jockey_history_samples']=statistics.get(horse['jockey_id'],{}).get('samples',0)
                horses.append(horse)
            if len(horses)<3:raise ValueError('insufficient active runners')
            published=all(h['number'] is not None for h in horses)
            for h in horses:h['display_key']=h['number'] if published else '馬番未定:'+h['name']
            if not published and any(h['number'] is not None for h in horses):raise ValueError('partly published field')
            # Independent netkeiba source check uses names, never unannounced order as numbers.
            net=observation['netkeiba']
            netnames=set()
            if not net.get('error'):
                for row in net['rows']:
                    if not any('Horse_Info' in c['class'] for c in row['cells']):continue
                    for link in row['links']:
                        if '/horse/' in link['href'] and link['text'].endswith('のデータベース'):
                            netnames.add(norm(link['text'][:-len('のデータベース')]))
                active_names={norm(h['name']) for h in horses}
                if netnames!=set(rowmap) and netnames!=active_names:raise ValueError('independent netkeiba runner set mismatch')
            else:raise ValueError('independent netkeiba card unavailable')
            features=overlay([feature(h) for h in horses],horses,NAMES,statistics)
            marginal,_=model.predict(features);internal=[float(p) for p in marginal[:,0]]
            external_by_name={norm(r['name']):r['index'] for r in base['external_indices']}
            if len(external_by_name)!=len(base['external_indices']):raise ValueError('duplicate external runner')
            e=[math.exp((external_by_name[norm(h['name'])]-max(external_by_name.values()))/20) for h in horses]
            external=[p/sum(e) for p in e]
            ticket_horses=[dict(h,number=h['display_key']) for h in horses]
            models={key:calculate_model(ticket_horses,[a*x+(1-a)*y for x,y in zip(internal,external)]) for key,a in [('A',1),('B',.75),('C',.5),('D',.25)]}
            for m in models.values():
                for column in ('p1','p2','p3'):
                    if abs(sum(h[column] for h in m['horses'])-1)>1e-9:raise ValueError('probability mass mismatch')
            quotes=decode_odds(observation['odds'])
            if quotes['status']=='middle':
                if not published:raise ValueError('current odds cannot join unpublished numbers')
                for h in horses:
                    values=quotes.get('odds',{}).get('1',{}).get(str(h['number']).zfill(2))
                    if values is None or float(values[0])<=0:raise ValueError('missing active current win quote')
            output['races'].append({'date':date,'race':label,'track':base['track'],'race_number':base['race_number'],'surface':base['surface'],'off_at':base['off_at'],
                'runners':horses,'excluded':excluded,'number_published':published,'models':models,'quotes':quotes,
                'old_A':base['models']['A']['horses'],'source':snapshot['url'],'source_sha256':snapshot['sha256'],'source_asof':snapshot['at'],
                'independent_card_source':net['url'],'independent_card_sha256':net['sha256'],
                'external_source':base['external_source'],'external_sha256':base['external_sha256'],'external_basis':'reused_original_frozen_external_index_no_refresh'})
        except Exception as exc:
            output['race_failures'].append({'date':date,'race':label,'error':str(exc)})
    if len(output['races'])+len(output['race_failures'])!=46:raise ValueError('expected 46 flat races')
    return output

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('saturday','sunday','evidence','riders','output'):p.add_argument('--'+key,required=True)
    a=p.parse_args();dest=Path(a.output)
    if dest.exists():raise ValueError('immutable output exists')
    files=[a.saturday,a.sunday,a.evidence,a.riders]
    first,second,evidence,riders=[json.loads(Path(f).read_text()) for f in files]
    modelpath=ROOT/'keiba_v48/reports/exact_rank/model_lag7.json'
    model_sha=digest(modelpath)
    if first['research_model_sha256']!=model_sha or second['research_model_sha256']!=model_sha:raise ValueError('frozen model changed')
    result=recalculate({first['date']:first,second['date']:second},evidence,riders,RankModel.from_dict(json.loads(modelpath.read_text())))
    result['source_file_sha256']={role:digest(f) for role,f in zip(('saturday','sunday','evidence','riders'),files)}
    result['model_sha256']=model_sha;result['database_sha256']=riders['database_sha256']
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'races':len(result['races']),'failures':result['race_failures'],'runners':sum(len(r['runners']) for r in result['races'])},ensure_ascii=False))
