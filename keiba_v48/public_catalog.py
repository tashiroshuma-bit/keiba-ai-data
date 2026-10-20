"""Cache independently published registration/rider catalog evidence.

Never request the known-refused accessS/JBIS sources or substitute another
horse-profile route. HTTP403 observations stop later requests to that path.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
import requests
from annual_reports import fetch


def get(url, folder):
    parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.hostname!='www.jra.go.jp' or not parsed.path.startswith(('/datafile/resist/','/datafile/meikan/')):
        raise ValueError('independent public catalog URL required')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    stem=folder/hashlib.sha256(url.encode()).hexdigest()
    metadata=stem.with_suffix('.json');body=stem.with_suffix('.bin')
    if metadata.exists():
        meta=json.loads(metadata.read_text())
        if meta.get('http_status')==403:
            raise PermissionError('previous HTTP403; catalog access remains stopped')
        raw=body.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=meta['sha256']:
            raise ValueError('catalog cache hash mismatch')
        return raw,meta
    try:
        raw=fetch(url)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code==403:
            metadata.write_text(json.dumps(dict(url=url,http_status=403,observed_at=dt.datetime.now(dt.timezone.utc).isoformat())))
        raise
    meta=dict(url=url,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),http_status=200,
              observed_at=dt.datetime.now(dt.timezone.utc).isoformat(),local_path=str(body.resolve()))
    body.write_bytes(raw);metadata.write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    return raw,meta
