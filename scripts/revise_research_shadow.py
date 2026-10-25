"""Write a new immutable shadow revision after evidenced preoff scratches.

Usage: python scripts/revise_research_shadow.py BASE_JSON REQUEST_JSON OUTPUT_JSON
Request: race, parent_prediction_sha256 (BASE file bytes), parent_variant,
variant (same as parent), frozen_at, scheduled_start, nonstarter_evidence
[{no, source_url, observed_at}]. No arbitrary market/weight/going coefficients.
"""
import argparse
from datetime import datetime
import hashlib
import itertools
import json
from pathlib import Path

from weekend_prediction_review import normalized, rank_distribution, validate_revision, wide_union


def time_value(value):
    t=datetime.fromisoformat(value)
    if t.tzinfo is None:raise ValueError('timezone required')
    return t


def build_revision(base_bytes, request):
    digest=hashlib.sha256(base_bytes).hexdigest()
    validate_revision({'prediction_sha256':digest,'variant':request['parent_variant']},request)
    if request['variant']!=request['parent_variant']:
        raise ValueError('This scratch-only command cannot switch probability variants')
    frozen,off=time_value(request['frozen_at']),time_value(request['scheduled_start'])
    if frozen>=off:raise ValueError('revision must be frozen before scheduled start')
    nonstarters=[]
    for item in request['nonstarter_evidence']:
        if not item['source_url'].startswith('https://') or time_value(item['observed_at'])>frozen:
            raise ValueError('invalid nonstarter evidence/asof')
        nonstarters.append(item['no'])
    base=json.loads(base_bytes)
    races=[r for r in base['races'] if r['race']==request['race']]
    if len(races)!=1:raise ValueError('race not unique in base')
    models={}
    for model,data in races[0]['models'].items():
        if not set(nonstarters)<=set(h['no'] for h in data['horses']):raise ValueError('unknown nonstarter')
        weights=normalized({h['no']:h['p1'] for h in data['horses']},nonstarters=nonstarters)
        marginal,triples=rank_distribution(weights)
        tables={'single':{(n,):p for n,p in weights.items()},'quinella':{},'trio':{},'wide':{}}
        for a,b in itertools.combinations(sorted(weights),2):
            tables['quinella'][a,b]=weights[a]*weights[b]*(1/(1-weights[a])+1/(1-weights[b]))
            tables['wide'][a,b]=wide_union(triples,[(a,b)])
        for triple,p in triples.items():
            key=tuple(sorted(triple));tables['trio'][key]=tables['trio'].get(key,0)+p
        priority={}
        for market,threshold in [('single',.4),('quinella',.25),('trio',.3)]:
            tickets=[];cumulative=0
            for nums,p in sorted(tables[market].items(),key=lambda item:(-item[1],item[0])):
                tickets.append({'numbers':list(nums),'p':p});cumulative+=p
                if cumulative>=threshold:break
            priority[market]={'count':len(tickets),'cumulative':cumulative,'tickets':tickets}
        names={h['no']:h.get('name','') for h in data['horses']}
        order=sorted(weights,key=lambda n:(-weights[n],n))
        models[model]={'horses':[{'no':n,'name':names[n],'p1':marginal[n][0],'p2':marginal[n][1],'p3':marginal[n][2]} for n in order],
            'top1_tied':sum(abs(weights[n]-weights[order[0]])<1e-9 for n in weights)>1,
            'priority':priority,
            'wide_all_pairs':[{'numbers':list(pair),'p':p} for pair,p in sorted(tables['wide'].items(),key=lambda x:(-x[1],x[0]))],
            'wide_selection':None}
    return {'schema':'research-shadow-revision-v1','status':'RESEARCH_NOT_CALIBRATED',
            'request':request,'parent_prediction_sha256':digest,'variant':request['variant'],
            'production_promoted':False,'races':[{'race':request['race'],'models':models}]}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('request',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args()
    result=build_revision(args.base.read_bytes(),json.loads(args.request.read_text()))
    with args.output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
