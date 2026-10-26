"""As-of horse, jockey and pair indices. Scores are not winning probabilities.

Joint ridge decomposition of field-centred performance estimates horse and rider
components together. It is an observational adjustment, not causal separation.
"""
import collections
import datetime as dt
import math
import numpy as np
from features import IdentityMap,finish,timestamp

HEADS=('finish_performance','win_share','top2_share','top3_share')
SETTINGS=dict(horse_penalty=5.,jockey_penalty=50.,iterations=80,descriptive_prior=5.,pair_penalty=10.)


def targets(rows):
    ranks=[]
    for row in rows:
        rank=finish(row)
        if rank is None and row.get('runner_status')!='nonfinisher':raise ValueError('unresolved finish')
        ranks.append(float(rank) if rank else math.inf)
    ranks=np.asarray(ranks);n=len(rows)
    if n<3:raise ValueError('at least three runners required')
    if not np.any(ranks==1) or np.any(ranks[np.isfinite(ranks)]>n):raise ValueError('invalid complete-field ranks')
    performance=((ranks[:,None]<ranks[None,:]).sum(axis=1)+
                 .5*((ranks[:,None]==ranks[None,:]).sum(axis=1)-1))/(n-1)
    shares=[]
    for k in (1,2,3):
        values=[]
        for rank in ranks:
            if not math.isfinite(rank):values.append(0.);continue
            tied=sum(ranks==rank)
            values.append(max(0,min(tied,k-rank+1))/tied)
        v=np.asarray(values,float);shares.append(v-v.mean())
    return np.column_stack((performance-.5,*shares)),performance


def score(value):
    return float(np.clip(50+100*value,0,100))


def stats(rows):
    if not rows:return dict(starts=0,win_rate=None,top2_rate=None,top3_rate=None,performance_index=None)
    n=len(rows);perf=[r['_performance'] for r in rows]
    return dict(starts=n,win_rate=sum(finish(r)==1 for r in rows)/n,
        top2_rate=sum(finish(r) in (1,2) for r in rows)/n,
        top3_rate=sum(finish(r) in (1,2,3) for r in rows)/n,
        performance_index=100*(sum(perf)+SETTINGS['descriptive_prior']*.5)/(n+SETTINGS['descriptive_prior']))


class ActorIndices:
    def __init__(self,history,cutoff,exclude_race_id=None,allow_assumed=False):
        self.cutoff=timestamp(cutoff) if isinstance(cutoff,str) else cutoff
        self.by_kind={'horse':collections.defaultdict(list),'jockey':collections.defaultdict(list)}
        self.pairs=collections.defaultdict(list);self.horse={};self.jockey={};self.offsets={}
        grouped=collections.defaultdict(list);seen=set();identity=IdentityMap();rejected=collections.Counter()
        for original in history:
            if original.get('availability_basis','').startswith('assumed_') and not allow_assumed:
                raise ValueError('assumed availability cannot enter observed actor indices')
            off=timestamp(original['off_timestamp']);available=timestamp(original['result_available_at'])
            if available<off:raise ValueError('result available before race')
            if off>=self.cutoff or available>self.cutoff or original['race_id']==exclude_race_id:continue
            if not str(original.get('source_url','')).startswith('https://'):raise ValueError('history source required')
            key=(original['race_id'],str(original['horse_number']))
            if key in seen:raise ValueError('duplicate historical runner')
            seen.add(key);row=dict(original)
            for kind in ('horse','jockey'):
                value=row.get(kind+'_id')
                if value and not value.startswith('unlinked:'):identity.resolve(kind,value)
            grouped[row['race_id']].append(row)
        complete=[]
        for rid,rows in sorted(grouped.items()):
            counts=[int(r.get('field_size') or r.get('expected_runners') or 0) for r in rows]
            if (not counts or min(counts)<3 or len(set(counts))!=1 or len(rows)>counts[0] or
                    len({r['off_timestamp'] for r in rows})!=1):
                rejected['invalid_field_metadata']+=1;continue
            for kind in ('horse','jockey'):
                ids=[r.get(kind+'_id') for r in rows if r.get(kind+'_id') and not r[kind+'_id'].startswith('unlinked:')]
                if len(ids)!=len(set(ids)):raise ValueError('duplicate '+kind+' identity in one race')
            for row in rows:
                rank=finish(row)
                if (rank is None and row.get('runner_status')!='nonfinisher') or (rank and rank>counts[0]):
                    raise ValueError('invalid observed rank')
                # Keep individual observations when other runners lack IDs.
                # Equal printed ranks receive equal descriptive values.
                row['_performance']=1-(rank-1)/(counts[0]-1) if rank else 0.
                for kind in ('horse','jockey'):
                    ident=row.get(kind+'_id')
                    if ident and not ident.startswith('unlinked:'):self.by_kind[kind][ident].append(row)
                hid,jid=row.get('horse_id'),row.get('jockey_id')
                if hid and jid and not hid.startswith('unlinked:') and not jid.startswith('unlinked:'):
                    self.pairs[hid,jid].append(row)
            if len(rows)!=counts[0]:
                rejected['incomplete_field']+=1;continue
            try:y,perf=targets(rows)
            except ValueError:rejected['unresolved_finish']+=1;continue
            for row,value in zip(rows,perf):row['_adjusted_performance']=float(value)
            if any(not r.get('horse_id') or r['horse_id'].startswith('unlinked:') or not r.get('jockey_id') for r in rows):
                rejected['identity_incomplete_for_adjustment']+=1;continue
            complete.append((rid,rows,y))
        for groups in self.by_kind.values():
            for rows in groups.values():rows.sort(key=lambda r:(timestamp(r['off_timestamp']),r['race_id']))
        self.audit=dict(cutoff=self.cutoff.isoformat(),excluded_race_id=exclude_race_id,
            available_fields=len(grouped),adjusted_fields=len(complete),rejected=dict(rejected),
            horse_ids=len(self.by_kind['horse']),jockey_ids=len(self.by_kind['jockey']),
            availability='assumed_research' if allow_assumed else 'actual_observed',
            probability_model_changed=False,method='joint_field_centered_ridge',settings=SETTINGS.copy())
        if not complete:return
        horses=sorted({r['horse_id'] for _,rs,_ in complete for r in rs})
        jockeys=sorted({r['jockey_id'] for _,rs,_ in complete for r in rs})
        hi={h:i for i,h in enumerate(horses)};ji={j:i for i,j in enumerate(jockeys)}
        self.horse_ids=horses;self.jockey_ids=jockeys
        h=np.array([hi[r['horse_id']] for _,rs,_ in complete for r in rs]);j=np.array([ji[r['jockey_id']] for _,rs,_ in complete for r in rs])
        sizes=np.array([len(rs) for _,rs,_ in complete]);starts=np.r_[0,np.cumsum(sizes)[:-1]]
        y=np.vstack([v for _,_,v in complete]);hc=np.bincount(h);jc=np.bincount(j)
        H=np.zeros((len(horses),4));J=np.zeros((len(jockeys),4));offset=np.zeros((len(complete),4))
        # Coordinate descent for sum ||y-H-J-offset_race||² + ridge penalties.
        for _ in range(SETTINGS['iterations']):
            repeated=np.repeat(offset,sizes,axis=0)
            for k in range(4):H[:,k]=np.bincount(h,weights=y[:,k]-J[j,k]-repeated[:,k],minlength=len(H))/(hc+SETTINGS['horse_penalty'])
            for k in range(4):J[:,k]=np.bincount(j,weights=y[:,k]-H[h,k]-repeated[:,k],minlength=len(J))/(jc+SETTINGS['jockey_penalty'])
            offset=np.add.reduceat(y-H[h]-J[j],starts,axis=0)/sizes[:,None]
        for key,i in hi.items():self.horse[key]=(H[i],int(hc[i]))
        for key,i in ji.items():self.jockey[key]=(J[i],int(jc[i]))
        for (rid,_,_),value in zip(complete,offset):self.offsets[rid]=value
        self.audit['adjusted_starts']=len(y)
        self.audit['ridge_objective']=float(np.square(y-H[h]-J[j]-np.repeat(offset,sizes,axis=0)).sum()+
            SETTINGS['horse_penalty']*np.square(H).sum()+SETTINGS['jockey_penalty']*np.square(J).sum())
        residual=H[h]+J[j]+np.repeat(offset,sizes,axis=0)-y
        check=[]
        for k in range(4):
            check.append(float(np.max(np.abs((np.bincount(h,weights=residual[:,k],minlength=len(H))+SETTINGS['horse_penalty']*H[:,k])/(hc+SETTINGS['horse_penalty'])))))
            check.append(float(np.max(np.abs((np.bincount(j,weights=residual[:,k],minlength=len(J))+SETTINGS['jockey_penalty']*J[:,k])/(jc+SETTINGS['jockey_penalty'])))))
        self.audit['max_normal_equation_step']=max(check)
        self.audit['solver_within_1e_4']=max(check)<1e-4

    def entity(self,kind,identity,context=None):
        if kind not in ('horse','jockey'):raise ValueError('unknown entity kind')
        rows=self.by_kind[kind].get(identity,[]);rating=(self.horse if kind=='horse' else self.jockey).get(identity)
        penalty=SETTINGS['horse_penalty' if kind=='horse' else 'jockey_penalty']
        other='jockey_id' if kind=='horse' else 'horse_id'
        partners={r.get(other) for r in rows if r.get(other) and not r[other].startswith('unlinked:')}
        adjusted_partners={r.get(other) for r in rows if r['race_id'] in self.offsets and r.get(other)}
        result=dict(id=identity,observed=bool(rows),overall=stats(rows),adjusted_indices=None,
            counterpart_count=len(partners),adjusted_counterpart_count=len(adjusted_partners),
            adjusted_starts=rating[1] if rating else 0,sample_support=rating[1]/(rating[1]+penalty) if rating else 0,
            score_scale='0-100; 50=zero estimated component; not win probability',
            adjustment_role='observational joint estimate; not causal separation')
        if rating:result['adjusted_indices']={name:score(value) for name,value in zip(HEADS,rating[0])}
        if kind=='horse':result['recent5']=stats(rows[-5:])
        if kind=='jockey':result['recent90days']=stats([r for r in rows if timestamp(r['off_timestamp'])>=self.cutoff-dt.timedelta(days=90)])
        if context:
            same_surface=lambda r:r.get('surface')==context.get('surface')
            result['conditions']={
                'course':stats([r for r in rows if same_surface(r) and r.get('track')==context.get('track')]),
                'distance':stats([r for r in rows if same_surface(r) and abs(float(r['distance_m'])-float(context['distance_m']))<=200]),
                'going':stats([r for r in rows if same_surface(r) and context.get('going') and r.get('going')==context['going']]),
                'class':stats([r for r in rows if context.get('class_level') is not None and r.get('class_level')==context['class_level']])}
        return result

    def pair(self,horse_id,jockey_id):
        rows=self.pairs.get((horse_id,jockey_id),[]);h=self.horse.get(horse_id);j=self.jockey.get(jockey_id)
        residual=[]
        if h and j:
            for r in rows:
                if r['race_id'] in self.offsets:
                    residual.append(r['_adjusted_performance']-.5-h[0][0]-j[0][0]-self.offsets[r['race_id']][0])
        return dict(horse_id=horse_id,jockey_id=jockey_id,overall=stats(rows),adjusted_pair_starts=len(residual),
            compatibility_index=score(sum(residual)/(len(residual)+SETTINGS['pair_penalty'])) if residual else None,
            role='shrunk in-sample residual; not validated extra winning probability')

    def runners(self,rows):
        out=[]
        for row in rows:
            hid,jid=row['horse_id'],row.get('jockey_id');past=self.by_kind['horse'].get(hid,[])
            prior_jockey=past[-1].get('jockey_id') if past else None
            current=self.jockey.get(jid);previous=self.jockey.get(prior_jockey)
            out.append(dict(horse_number=str(row['horse_number']),horse=self.entity('horse',hid,row),
                jockey=self.entity('jockey',jid,row),pair=self.pair(hid,jid),
                jockey_change=dict(previous_jockey_id=prior_jockey,changed=bool(prior_jockey and prior_jockey!=jid),
                    current_snapshot_index_delta=(score(current[0][0])-score(previous[0][0])) if current and previous else None),
                used_as_new_probability_features=False))
        return out
