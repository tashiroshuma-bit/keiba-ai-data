"""Package both fixed-protocol audit runs and verify every persisted artifact."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil


def sha(data):
    return hashlib.sha256(data).hexdigest()


def package(repo,results):
    root=Path(repo).resolve();results=Path(results).resolve()
    dest=root/'keiba_v48/reports/deep_audit';dest.mkdir(parents=True,exist_ok=True)
    inventory=[];comparisons={}
    for source,sub in [('replay','pre_class_fix'),('class_repair','')]:
        folder=results/source;target=dest/sub;target.mkdir(parents=True,exist_ok=True)
        comparisons[source]=[]
        for lag in (2,7):
            report=json.loads((folder/f'repair_comparison_lag{lag}.json').read_text())
            comparisons[source].append(report)
            for filename,expected in report['source_code_sha256'].items():
                file=root/'keiba_v48'/filename
                if sha(file.read_bytes())!=expected:
                    archived=dest/'pre_class_fix/source'/filename
                    if source!='replay' or not archived.is_file() or sha(archived.read_bytes())!=expected:
                        raise ValueError('source hash does not match run: '+filename)
            for filename,expected in report['artifact_sha256'].items():
                if sha((folder/filename).read_bytes())!=expected:raise ValueError('artifact hash mismatch: '+filename)
            raw=(folder/f'repair_predictions_lag{lag}.json').read_bytes()
            if sha(raw)!=report['prediction_sha256']:raise ValueError('prediction hash mismatch')
        for file in sorted(folder.glob('*.json')):
            raw=file.read_bytes();name=file.name+('.gz' if len(raw)>200000 else '')
            data=gzip.compress(raw,mtime=0) if name.endswith('.gz') else raw
            output=target/name;output.write_bytes(data)
            restored=gzip.decompress(output.read_bytes()) if name.endswith('.gz') else output.read_bytes()
            if restored!=raw:raise ValueError('packaged bytes mismatch')
            inventory.append(dict(file=str(output.relative_to(dest)),stored_sha256=sha(data),uncompressed_sha256=sha(raw),uncompressed_bytes=len(raw)))
    for src,name in [('data_audit_lag2.json','data_audit_before_class.json'),('class_data_audit_lag2.json','data_audit_lag2.json')]:
        shutil.copyfile(results/src,dest/name)
    (dest/'artifact_inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n')
    comparison=[]
    for before,after in zip(comparisons['replay'],comparisons['class_repair']):
        key='exact_original_EV_cohort_structural_vs_original'
        prior=before[key];current=after[key]
        comparison.append(dict(lag_days=after['lag_days'],races=current['races'],baseline=current['baseline'],
                               before_class_fix=prior['candidate'],after_class_fix=current['candidate'],
                               before_EV=prior['candidate_EV'],after_EV=current['candidate_EV'],
                               day_profit_delta_interval=current['paired_day_95pct_profit_delta_yen_per_race'],
                               selected_structural=after['selected_structural'],
                               full_market_baseline=after['full_market_cohort_vs_market']['baseline'],
                               full_market_candidate=after['full_market_cohort_vs_market']['candidate']))
    (dest/'before_after_summary.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2)+'\n')
    return dict(packaged_files=len(inventory),stored_bytes=sum((dest/x['file']).stat().st_size for x in inventory),comparisons=comparison)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',default=str(Path(__file__).resolve().parents[1]));p.add_argument('--results',required=True);a=p.parse_args()
    print(json.dumps(package(a.repo,a.results),ensure_ascii=False))
