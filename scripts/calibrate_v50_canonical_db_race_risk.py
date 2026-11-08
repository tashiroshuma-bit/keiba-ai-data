"""2025-only out-of-time calibration + 2026 untouched hard-race test.

Real canonical DB v10 2023/24 retrained research candidate input.
No final-odds feature, no outcome information in any target's features.
"""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import sys,json,math
from pathlib import Path
try:
    from scripts import retrain_v50_canonical_db_shadow as pipe
except ModuleNotFoundError:
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    import retrain_asof_v50_research as pipe
import numpy as np
from scipy.optimize import minimize,minimize_scalar
from scipy.special import expit
from scipy.stats import rankdata
OUT=Path(os.environ.get('KEIBA_RETRAIN_OUTPUT_DIR','/mnt/data/keiba'))

def power(p,temperature):
    z=np.where(p>0,p**(1/temperature),0.)
    return z/z.sum(axis=1,keepdims=True)

def ex_likelihood(p,w):
    return float(-np.log(np.maximum(p[np.arange(len(w)),w],1e-12)).mean())

def auc(y,score):
    pos=y==1;negative=y==0
    if not pos.any() or not negative.any():return None
    rk=rankdata(score)
    return float((rk[pos].sum()-pos.sum()*(pos.sum()+1)/2)/(pos.sum()*negative.sum()))

def risk_features(rows,p):
    arr=[];Y=[]
    for i,r in enumerate(rows):
        n=r['field'];q=p[i,:n]
        order=np.argsort(-q,kind='stable')
        peak=q[order[0]]
        ent=-sum(float(x)*math.log(float(x)) for x in q if x>0)/math.log(n)
        arr.append([sum(q[order[:3]]),peak,float(q[order[0]]-q[order[1]]),ent,n/18.,
                    float(r['horse_unknown_frac']),float(r['juvenile_or_new_frac']),int(r['surface']=='dirt')])
        Y.append(int(r['winner'] not in order[:3]))
    return np.array(arr),np.array(Y)

def fit_binary(X,y):
    m=X.mean(axis=0);s=np.maximum(X.std(axis=0),.05)
    z=(X-m)/s
    def function(w):
        v=z@w[:-1]+w[-1]
        p=expit(v)
        ll=np.mean(np.logaddexp(0,v)-y*v)+.15/2*(w[:-1]@w[:-1])
        g=z.T@(p-y)/len(y)+.15*w[:-1]
        return ll,np.r_[g,np.mean(p-y)]
    fit=minimize(function,np.zeros(z.shape[1]+1),jac=True,method='L-BFGS-B')
    if not fit.success:raise ValueError('binary calibration fit failed '+str(fit.message))
    return {'mean':m,'std':s,'coefs':fit.x[:-1],'intercept':fit.x[-1]}

def prob_binary(x,model):return expit(((x-model['mean'])/model['std'])@model['coefs']+model['intercept'])

def risk_metrics(y,p):
    eps=np.clip(p,1e-7,1-1e-7)
    return {'n':len(y),'missed_top3':int(y.sum()),'rate':float(y.mean()),
            'logloss':float(np.mean(-y*np.log(eps)-(1-y)*np.log(1-eps))),
            'brier':float(np.mean((p-y)**2)),'auc':auc(y,p)}

def main():
    pipe.verify_canonical_database()
    asset=json.load(open(OUT/'retrained_canonical_db_v10_horse_jockey_research.json'))
    events,_=pipe.fetch();rows,_=pipe.create_rows(events)
    peryear={year:[r for r in rows if r['date'][:4]==year] for year in ['2025','2026']}
    m=asset['research_model'];model={'mean':np.array(m['mean']), 'scale':np.array(m['scale']),
      'weights':np.array(m['coefficients']),'features':m['selected_features']}
    calc={year:pipe.predict(records,model) for year,records in peryear.items()}
    calib=peryear['2025'];q=calc['2025'];y=np.array([r['winner'] for r in calib])
    best=minimize_scalar(lambda t:ex_likelihood(power(q,t),y),bounds=(.65,3.0),method='bounded',options={'xatol':1e-7})
    if not best.success:raise ValueError('temperature optim failed')
    temp=float(best.x)
    baseline=pipe.score(peryear['2026'],calc['2026'])
    adjusted=pipe.score(peryear['2026'],power(calc['2026'],temp))
    record={'temperature_2025_only':temp,'2025_calibration_n':len(calib),
      '2025_logloss_before':ex_likelihood(q,y),'2025_logloss_after':ex_likelihood(power(q,temp),y),
      '2026_unseen_before':baseline,'2026_unseen_after':adjusted}
    # Risk: 2025 y labels are the true class, but not 2026 or latest odds.
    A,yA=risk_features(calib,power(q,temp))
    B,yB=risk_features(peryear['2026'],power(calc['2026'],temp))
    clf=fit_binary(A,yA)
    old_risk=1-B[:,0];new_risk=prob_binary(B,clf)
    record['top3_failure_risk_model']={
      'features':['model_top3_mass','model_top1_p','top1_vs_2_gap','race_entropy','field_size_18',
                  'missing_horse_id_fraction','novice_fraction','dirt_flag'],
      'training_n_2025':len(yA),'test_n_2026':len(yB),
      '2026_uncalibrated_base':risk_metrics(yB,old_risk),
      '2026_adjusted':risk_metrics(yB,new_risk),
      'train_means':list(map(float,clf['mean'])),'train_scales':list(map(float,clf['std'])),
      'coefficients':list(map(float,clf['coefs'])),'intercept':float(clf['intercept'])}
    # Determine all operating thresholds from 2025 training/calibration only.
    in_sample_risk=prob_binary(A,clf)
    high_cutoff=float(np.quantile(in_sample_risk,.8))
    low_cutoff=float(np.quantile(in_sample_risk,.2))
    record['top3_failure_risk_model']['fixed_high_risk_cutoff_from_2025']=high_cutoff
    record['top3_failure_risk_model']['fixed_low_risk_cutoff_from_2025']=low_cutoff
    high=np.where(new_risk>=high_cutoff)[0]
    low=np.where(new_risk<=low_cutoff)[0]
    record['top3_failure_risk_model']['fixed_2025_threshold_high_risk']={'n':len(high),'misses':int(yB[high].sum()),'miss_rate':float(yB[high].mean()) if len(high) else None,'mean_predicted_risk':float(new_risk[high].mean()) if len(high) else None}
    record['top3_failure_risk_model']['fixed_2025_threshold_low_risk']={'n':len(low),'misses':int(yB[low].sum()),'miss_rate':float(yB[low].mean()) if len(low) else None,'mean_predicted_risk':float(new_risk[low].mean()) if len(low) else None}
    record['status']='real_DB_2025_temperature_and_failure_calibration_2026_holdout_not_canonical_v50'
    record['source_model']='retrained_canonical_db_v10_horse_jockey_research.json'
    record['no_formal_v50_production_change']=True
    record['note']='Conditional top3 failure predictions are risk warnings; they do NOT change horse rankings or reward rare-upset horses.'
    (OUT/'calibrated_canonical_db_v10_weak_race_risk.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    L=['# JRA正本DB v10｜2025年で確率校正・2026年未学習レースで評価','',
       '2023/24で馬・騎手再学習済の研究モデル。2025年だけで温度・予測失敗分類器を学習し、2026年は評価のみ。',
       f'確率温度 {temp:.3f}（2025年2,890Rで選択）。2025 Log Loss {record["2025_logloss_before"]:.4f}→{record["2025_logloss_after"]:.4f}。','',
       '|2026年2,384R|未校正|校正後|','|---|---:|---:|',
       f'|1着指名|{baseline["top1"]}/{baseline["n"]} ({baseline["top1_rate"]:.1%})|{adjusted["top1"]}/{adjusted["n"]} ({adjusted["top1_rate"]:.1%})|',
       f'|勝馬上位3捕捉|{baseline["winner_top3"]}/{baseline["n"]} ({baseline["winner_top3_rate"]:.1%})|{adjusted["winner_top3"]}/{adjusted["n"]} ({adjusted["winner_top3_rate"]:.1%})|',
       f'|Log Loss|{baseline["logloss"]:.4f}|{adjusted["logloss"]:.4f}|',
       f'|Brier|{baseline["brier"]:.4f}|{adjusted["brier"]:.4f}|','',
       '## 勝馬を上位3頭に拾えないレースの事前リスク分類','',
       '|2026年2,384Rで評価|確率質 Brier|LogLoss|AUC|',
       '|---|---:|---:|---:|']
    for label,v in [('元の上位3頭予測確率に基づく失敗確率',record['top3_failure_risk_model']['2026_uncalibrated_base']),
                    ('2025年で学習した失敗リスク分類器',record['top3_failure_risk_model']['2026_adjusted'])]:
        L.append(f'|{label}|{v["brier"]:.4f}|{v["logloss"]:.4f}|{v["auc"]:.4f}|')
    for label in ('fixed_2025_threshold_high_risk','fixed_2025_threshold_low_risk'):
        t=record['top3_failure_risk_model'][label]
        L.append(f'- {label}: {t["misses"]}/{t["n"]} ({t["miss_rate"]:.1%})、予測失敗率平均 {t["mean_predicted_risk"]:.1%}')
    L+=['','リスクは通常レースを区別する「予測難易度」の指標であり、珍しい超大波乱を予言するものではない。','正式v50の係数、順位、予測配信は変更しない。']
    (OUT/'calibrated_canonical_db_v10_weak_race_risk.md').write_text('\n'.join(L)+'\n')
    print(json.dumps({'temperature':temp,'2026_before':baseline,'2026_after':adjusted,
      'risk':record['top3_failure_risk_model']['2026_adjusted'],
      'base_risk':record['top3_failure_risk_model']['2026_uncalibrated_base'],
      'highest_risk':record['top3_failure_risk_model']['fixed_2025_threshold_high_risk'],
      'lowest_risk':record['top3_failure_risk_model']['fixed_2025_threshold_low_risk']},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
