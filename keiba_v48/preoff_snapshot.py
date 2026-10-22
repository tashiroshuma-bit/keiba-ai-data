"""Explicit preoff field provenance; unknown observations remain missing."""
import datetime as dt
import hashlib
import math
from urllib.parse import urlparse
from features import timestamp

JST=dt.timezone(dt.timedelta(hours=9))


def source_proof(row, prefix, now, cutoff):
    at=row.get(prefix+'_asof');url=row.get(prefix+'_source_url');digest=row.get(prefix+'_source_sha256')
    if (not at or not isinstance(url,str) or not url.startswith('https://')
            or not isinstance(digest,str) or len(digest)!=64
            or any(c not in '0123456789abcdef' for c in digest)):
        raise ValueError(prefix+' requires observation and source hash')
    if timestamp(at)>min(now,cutoff):raise ValueError('future '+prefix+' observation')
    return timestamp(at)


def audit_snapshot(rows,now,cutoff):
    counts={k:0 for k in ('sex_age','gate','carried_weight','going','jockey_id')}
    for row in rows:
        if row.get('sex_age'):
            if '(cid:' in str(row['sex_age']):raise ValueError('unresolved sex/age glyph in current card')
            counts['sex_age']+=1
        if row.get('gate') is not None:
            v=row['gate']
            if isinstance(v,bool) or not 1<=float(v)<=8 or float(v)!=int(float(v)):
                raise ValueError('invalid preoff gate')
            counts['gate']+=1
        if row.get('carried_weight') is not None:
            value=float(row['carried_weight'])
            if (not math.isfinite(value) or not 30<=value<=80
                    or row.get('carried_weight_basis')!='announced_preoff'):
                raise ValueError('announced preoff carried weight required')
            source_proof(row,'carried_weight',now,cutoff);counts['carried_weight']+=1
        if row.get('going'):
            at=source_proof(row,'going',now,cutoff)
            if (row['going'] not in ('良','稍重','重','不良')
                    or at.astimezone(JST).date()!=timestamp(row['off_timestamp']).astimezone(JST).date()):
                raise ValueError('same-race-day observed going required')
            counts['going']+=1
        counts['jockey_id']+=bool(row.get('jockey_id'))
    return dict(active_runners=len(rows),present=counts,
        missing={k:len(rows)-n for k,n in counts.items()},
        missing_values_imputed=False,final_result_fields_allowed=False)


def static_card_status(body,meta):
    """Inspect the independently accessible static entry page, never JRADB links."""
    from official_linkage import parse_html
    url=urlparse(meta['url'])
    if (url.scheme!='https' or url.hostname!='www.jra.go.jp'
            or not url.path.startswith('/keiba/') or not url.path.endswith('/syutsuba.html')):
        raise ValueError('static official entry page required')
    if hashlib.sha256(body).hexdigest()!=meta['sha256']:raise ValueError('entry source hash mismatch')
    text=parse_html(body,'lxml').get_text(' ',strip=True)
    pending='出馬表は、' in text and '公開予定です' in text
    return dict({**meta,'http_status':meta.get('status'),'status':'publication_pending' if pending else 'requires_card_parser_review'},
        full_field_attested=False,forecast_created=False,
        missing=['complete_active_field','official_identity_links','gate','announced_carried_weight','race_day_going'],
        note='Publication notice is not an actual publication timestamp or a complete runner field.')
