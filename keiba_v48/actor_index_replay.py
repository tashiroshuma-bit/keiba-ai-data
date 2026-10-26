"""Fast as-of reconstruction of the unchanged joint horse/jockey index objective."""
import collections
import hashlib
import numpy as np
from actor_indices import SETTINGS,targets
from features import IdentityMap,timestamp
from validation import canonical


class ActorReplay:
    def __init__(self,history):
        grouped=collections.defaultdict(list);seen=set();identity=IdentityMap();self.rejected=collections.Counter()
        for row in history:
            key=row['race_id'],str(row['horse_number'])
            if key in seen:raise ValueError('duplicate historical runner')
            seen.add(key)
            if timestamp(row['result_available_at'])<timestamp(row['off_timestamp']):raise ValueError('result precedes off')
            grouped[row['race_id']].append(row)
        events=[]
        for rid,rows in sorted(grouped.items()):
            counts=[int(r.get('field_size') or r.get('expected_runners') or 0) for r in rows]
            if len(rows)<3 or any(n!=len(rows) for n in counts):
                self.rejected['incomplete_field']+=1;continue
            if len({r['off_timestamp'] for r in rows})!=1:raise ValueError('inconsistent off')
            if any(not r.get('horse_id') or r['horse_id'].startswith('unlinked:') or not r.get('jockey_id') for r in rows):
                self.rejected['missing_identity']+=1;continue
            for kind in ('horse','jockey'):
                ids=[identity.resolve(kind,r[kind+'_id']) for r in rows]
                if len(ids)!=len(set(ids)):raise ValueError('duplicate entity in field')
            try:y,_=targets(rows)
            except ValueError:self.rejected['unresolved_finish']+=1;continue
            events.append((rid,rows,y))
        self.events=events
        self.hids={v:i for i,v in enumerate(sorted({r['horse_id'] for _,rs,_ in events for r in rs}))}
        self.jids={v:i for i,v in enumerate(sorted({r['jockey_id'] for _,rs,_ in events for r in rs}))}
        self.sizes=np.array([len(rs) for _,rs,_ in events],int)
        self.event_starts=np.r_[0,np.cumsum(self.sizes)[:-1]]
        self.availability=np.array([max(timestamp(r['result_available_at']).timestamp() for r in rs) for _,rs,_ in events])
        self.off=np.array([timestamp(rs[0]['off_timestamp']).timestamp() for _,rs,_ in events])
        self.h=np.array([self.hids[r['horse_id']] for _,rs,_ in events for r in rs],int)
        self.j=np.array([self.jids[r['jockey_id']] for _,rs,_ in events for r in rs],int)
        self.y=np.vstack([v for _,_,v in events]) if events else np.zeros((0,4))
        self.H=np.zeros((len(self.hids),4));self.J=np.zeros((len(self.jids),4))
        self.hc=np.zeros(len(self.hids),int);self.jc=np.zeros(len(self.jids),int)
        self.offset=np.zeros((len(events),4));self.last_cutoff=None;self.key=None;self.snapshots=[]

    def fit_before(self,cutoff):
        cutoff=timestamp(cutoff) if isinstance(cutoff,str) else cutoff
        if self.last_cutoff is not None and cutoff<self.last_cutoff:raise ValueError('replay cutoffs must be chronological')
        self.last_cutoff=cutoff;at=cutoff.timestamp()
        selected=np.flatnonzero((self.availability<=at)&(self.off<at));key=tuple(map(int,selected))
        if key==self.key:return self.snapshot
        self.key=key
        if not len(selected):
            self.H.fill(0);self.J.fill(0);self.hc.fill(0);self.jc.fill(0);error=0
        else:
            ix=np.concatenate([np.arange(self.event_starts[i],self.event_starts[i]+self.sizes[i]) for i in selected])
            h,j,y=self.h[ix],self.j[ix],self.y[ix];sizes=self.sizes[selected];starts=np.r_[0,np.cumsum(sizes)[:-1]]
            self.hc=np.bincount(h,minlength=len(self.H));self.jc=np.bincount(j,minlength=len(self.J))
            H,J=self.H,self.J;offset=self.offset[selected].copy()
            for _ in range(SETTINGS['iterations']):
                repeated=np.repeat(offset,sizes,axis=0)
                for k in range(4):H[:,k]=np.bincount(h,weights=y[:,k]-J[j,k]-repeated[:,k],minlength=len(H))/(self.hc+SETTINGS['horse_penalty'])
                for k in range(4):J[:,k]=np.bincount(j,weights=y[:,k]-H[h,k]-repeated[:,k],minlength=len(J))/(self.jc+SETTINGS['jockey_penalty'])
                offset=np.add.reduceat(y-H[h]-J[j],starts,axis=0)/sizes[:,None]
            self.offset[selected]=offset
            residual=H[h]+J[j]+np.repeat(offset,sizes,axis=0)-y;steps=[]
            for k in range(4):
                steps.append(np.max(np.abs((np.bincount(h,weights=residual[:,k],minlength=len(H))+SETTINGS['horse_penalty']*H[:,k])/(self.hc+SETTINGS['horse_penalty']))))
                steps.append(np.max(np.abs((np.bincount(j,weights=residual[:,k],minlength=len(J))+SETTINGS['jockey_penalty']*J[:,k])/(self.jc+SETTINGS['jockey_penalty']))))
            error=float(max(steps))
        ids=[self.events[i][0] for i in selected]
        self.snapshot=dict(number=len(self.snapshots),cutoff=cutoff.isoformat(),races=len(ids),starts=int(self.sizes[selected].sum()),
            source_race_ids_sha256=hashlib.sha256(canonical(ids).encode()).hexdigest(),
            maximum_result_available_at=float(self.availability[selected].max()) if len(selected) else None,
            maximum_source_off=float(self.off[selected].max()) if len(selected) else None,
            maximum_normal_equation_step=error)
        if error>1e-4:raise ValueError('as-of index fit failed convergence')
        self.snapshots.append(self.snapshot.copy())
        return self.snapshot

    def scores(self,rows):
        h=[];j=[];hn=[];jn=[]
        for row in rows:
            hi=self.hids.get(row.get('horse_id'));ji=self.jids.get(row.get('jockey_id'))
            hc=int(self.hc[hi]) if hi is not None else 0;jc=int(self.jc[ji]) if ji is not None else 0
            h.append(np.clip(50+100*self.H[hi],0,100) if hc else np.full(4,50.))
            j.append(np.clip(50+100*self.J[ji],0,100) if jc else np.full(4,50.))
            hn.append(hc);jn.append(jc)
        return np.asarray(h),np.asarray(j),hn,jn


def index_picks(numbers,scores):
    scores=np.round(np.asarray(scores,float),8);numbers=list(map(int,numbers))
    if scores.shape!=(len(numbers),4) or len(numbers)<3 or not np.isfinite(scores).all():raise ValueError('complete index field required')
    def order(head):return sorted(range(len(numbers)),key=lambda i:(-scores[i,head],numbers[i]))
    win=order(1);ordered=order(0)[:3];trio=order(3)[:3]
    return dict(winner_pick=numbers[win[0]],ordered_pick=[numbers[i] for i in ordered],top3_pick=[numbers[i] for i in trio],
        winner_score=float(scores[win[0],1]),tied_top1=bool(sum(scores[:,1]==scores[win[0],1])>1))
