"""Independent strict promotion gate for 2026-10-25 research shadow predictions.
Exit 0 means the AUDIT RAN (not that promotion passed). Evidence file states verdict.
"""
import argparse,datetime as dt,hashlib,json,math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def audit(source,output):
    source=Path(source)
    d=json.loads(source.read_text())
    expected=35 # 36 scheduled, one obstacle outside flat-race model domain
    failures=[]
    if d.get('status')!='RESEARCH_SHADOW_UNCALIBRATED_NOT_V43_PRODUCTION':
        failures.append('UNEXPECTED_SOURCE_STATUS')
    if d.get('covered')!=expected:
        failures.append('NOT_ALL_35_FLAT_RACES_EVALUATED')
    if any(not (f.get('track')=='東京' and f.get('race')==4 and f.get('reason')=='OBSTACLE_OUT_OF_MODEL_DOMAIN') for f in d.get('failures',[])):
        failures.append('UNEXPECTED_EXCLUDED_OR_FAILED_RACES')
    if d.get('eligible')!=expected:
        failures.append('TOP5_NOT_SELECTED_FROM_ALL_35_FLAT_RACES')
    if not d.get('race_feature_pipeline_sha256'):
        failures.append('NO_TRAINING_IDENTICAL_FEATURE_PROVENANCE')
    if not d.get('official_horse_id_coverage'):
        failures.append('NO_VERIFIED_OFFICIAL_HORSE_ID_COVERAGE')
    if not d.get('verified_jockey_weight_gate_going_asof'):
        failures.append('MISSING_RACE_DAY_INPUT_ASOF_PROOF')
    if not d.get('calibration_report_sha256'):
        failures.append('NO_PROBABILITY_CALIBRATION_REPORT')
    if not d.get('prospective_prediction_frozen_sha256'):
        failures.append('NO_PROSPECTIVE_FROZEN_PREDICTION')
    if not d.get('independent_preoff_feature_replay'):
        failures.append('NO_INDEPENDENT_PREOFF_FEATURE_REPLAY')
    if not d.get('source_snapshot_sha256'):
        failures.append('NO_REPRODUCIBLE_SOURCE_SNAPSHOT')
    rows=d.get('races',[])
    if len(rows)!=d.get('covered'):failures.append('RACE_COUNT_MISMATCH')
    racekeys=set();integrity=[]
    for r in rows:
        key=(r['track'],r['race'])
        if key in racekeys:integrity.append('DUPLICATE_RACE:'+str(key))
        racekeys.add(key)
        nums=[x['number'] for x in r['ranked']]
        if len(nums)!=len(set(nums)) or len(nums)!=len(r['field']):
            integrity.append('DUPLICATE_OR_INCOMPLETE_RUNNERS:'+str(key))
        if abs(sum(x['p1'] for x in r['ranked'])-1)>1e-6:
            integrity.append('WIN_PROBABILITY_NOT_NORMALIZED:'+str(key))
        for label in ('win','quinella','trio'):
            b=r['tickets'][label]
            if b['count']!=len(b['tickets']) or b['coverage']<b['target']-1e-7:
                integrity.append('TICKET_COVERAGE_ERROR:'+str(key)+':'+label)
    model=json.loads((ROOT/'keiba_v48/reports/exact_rank/model_lag7.json').read_text())
    if model.get('research_only') is not True or model.get('live_eligible') is not False:
        integrity.append('MODEL_ARTIFACT_UNEXPECTED_DEPLOYMENT_STATUS')
    result=dict(schema='keiba-forecast-promotion-gate-v1',source_sha256=digest(source),
        source_races=d.get('covered'),source_eligible=d.get('eligible'),
        status='REJECTED_NOT_FORMAL_PREDICTION' if failures or integrity else 'PASSED_FORMAL_PREDICTION',
        technical_integrity='PASS' if not integrity else 'FAIL',
        formal_requirements_passed=not failures and not integrity,
        blockers=failures,integrity_errors=integrity,
        validation_baseline_2026_lag7={'first_pick_hit_rate':0.2013,'ordered_top3_hit_rate':0.0081,'unordered_top3_hit_rate':0.0362,'races':2707},
        note='Backtest baseline is an existing retrospective study, NOT prospective evidence for these 2026-10-25 predictions. Model coverage is not observed accuracy.')
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
    return result

if __name__=='__main__':
    a=argparse.ArgumentParser()
    a.add_argument('--source',default=str(ROOT/'reports/20261025_allrace_rank_shadow/all_races.json'))
    a.add_argument('--output',default=str(ROOT/'reports/20261025_allrace_rank_shadow/formal_validation_gate.json'))
    args=a.parse_args()
    verdict=audit(args.source,args.output)
    assert verdict['technical_integrity']=='PASS','TECHNICAL_INTEGRITY_FAILED'
    assert verdict['status']=='REJECTED_NOT_FORMAL_PREDICTION','INVALID_PROMOTION_GATE_TEST_EXPECTATION'
