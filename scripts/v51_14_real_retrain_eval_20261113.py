import os,sys,math,json,datetime,sqlite3,collections,importlib.util,csv,hashlib
from pathlib import Path
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import numpy as np
from scipy.optimize import minimize
D=Path('/mnt/data/v51_fouraxis_fullrun_20261113');FILES=Path('/mnt/data/files')
DB=FILES/'jra_2023_2025_v12_horse_ids_full_20261111.sqlite'
MODEL=FILES/'v51_rank_full_trained_2023_2024_cal2025.json'
GROUPS={'opponent_class':[0,1,2,3],'running_style':[4,5,6,7],'jockey_condition':[8,9,10],'previous_weight':[11,12,13],'combined':list(range(14))}
NAMES=['past_race_class_last3','past_rivals_prior_strength_last3','prior_class_missing','prior_rival_strength_missing','prior_corner4_fraction_last3','prior_early_style_last3','prior_corner_finish_gain_last3','prior_style_missing','jockey_track_surface_distance_residual','jockey_course_count_log','jockey_condition_missing','previous_reported_weight_delta_pct_last3','previous_weight_count_log','previous_weight_missing']
def log(*a):print(datetime.datetime.now().isoformat(timespec='seconds'),*a,flush=True)
def module(name,p):
 spec=importlib.util.spec_from_file_location(name,p);obj=importlib.util.module_from_spec(spec);sys.modules[name]=obj;spec.loader.exec_module(obj);return obj

def train_residual(b,extra,groups,ridge):
 idx=np.concatenate([g['indices'] for g in groups]);counts=np.array([len(g['indices']) for g in groups]);starts=np.r_[0,np.cumsum(counts)][:-1];correct=np.array([g['first'] for g in groups]);xx=extra[idx];yy=extra[correct].sum(axis=0);logit=b[idx];true=b[correct].sum()
 def fn(w):
  z=logit+xx@w;mx=np.maximum.reduceat(z,starts);p0=np.exp(z-np.repeat(mx,counts));sumz=np.add.reduceat(p0,starts);p=p0/np.repeat(sumz,counts)
  f=(sum(mx+np.log(sumz))-true-yy@w)/len(groups)+.5*ridge*(w@w)
  grad=(xx.T@p-yy)/len(groups)+ridge*w
  return float(f),grad
 r=minimize(fn,np.zeros(extra.shape[1]),jac=True,method='L-BFGS-B',options={'maxiter':125,'ftol':1e-9})
 if not r.success and r.jac@r.jac>1e-6:raise ValueError('training no convergence '+str(r.message))
 return r.x,{'iterations':r.nit,'converged':bool(r.success),'gradient_norm':float(np.linalg.norm(r.jac)),'nll_penalized':float(r.fun),'race_sets':len(groups),'runners':len(idx)}

def records(groups,base,extras,W,beta):
 out=[]
 for g in groups:
  ind=g['indices']
  out.append(([base[ind]+extras[ind]@beta,W[1][ind],W[2][ind]],g))
 return out

def cal_candidate(rank,recs,base_cal):
 gt=rank.temp_fit(recs,1)[0];temps={}
 for kind in ('high_entropy__close_field','high_entropy__clear_favorite','other_entropy__close_field','other_entropy__clear_favorite'):
  t,n=rank.temp_fit(recs,1,kind,gt);temps[kind]={'temp':t,'calibration_races':n,'fallback':n<75}
 return {'fitted_on':'2025_training_early_dates_only','global_stage_temperatures':{'1':gt,'2':base_cal['global_stage_temperatures']['2'],'3':base_cal['global_stage_temperatures']['3']},'winner_entropy_confidence_groups':temps,'group_entropy_cutoff':.94,'group_favorite_cutoff':.25,'minimum_group_count':75,'penalty_pseudoraces':125}

def assess(rank,record,cal):
 details=[]
 for z,g in record:
  raw=rank.softmax(z[0]);bucket=rank.bucket(raw);p=rank.softmax(z[0],cal['winner_entropy_confidence_groups'][bucket]['temp']);orig=g['indices'];true=int(np.where(orig==g['first'])[0][0]);pick=int(np.argmax(p));target=np.zeros(len(p));target[true]=1
  details.append({'race_id':g['race'],'date':g['date'],'hit':int(true==pick),'logloss':float(-math.log(max(p[true],1e-15))),'brier':float(np.sum((p-target)**2)),'confidence':float(p[pick]),'pred_local':pick,'true_local':true})
 bds=[.1,.15,.2,.3,.4,.5,1.01];bins=collections.defaultdict(list)
 for row in details:bins[next((i for i,b in enumerate(bds) if row['confidence']<b),len(bds)-1)].append(row)
 ece=sum(len(v)*abs(sum(z['confidence'] for z in v)/len(v)-sum(z['hit'] for z in v)/len(v)) for v in bins.values())/len(details)
 return {'races':len(details),'top1_hits':sum(z['hit'] for z in details),'top1_accuracy':float(np.mean([z['hit'] for z in details])),'winner_logloss':float(np.mean([z['logloss'] for z in details])),'winner_brier':float(np.mean([z['brier'] for z in details])),'ece_confidence':float(ece)},details

def boot_day(a,b,n=3000):
 days=collections.defaultdict(list)
 for x,y in zip(a,b):
  if x['race_id']!=y['race_id']:raise ValueError('race alignment mismatch')
  days[x['date']].append(y['hit']-x['hit'])
 keys=sorted(days);rng=np.random.default_rng(20261113);samples=[]
 for _ in range(n):
  nums=rng.integers(0,len(keys),size=len(keys));v=[x for i in nums for x in days[keys[int(i)]]];samples.append(sum(v)/len(v))
 return {'n_dates':len(keys),'n_races':len(a),'rate_delta':float(np.mean([y['hit']-x['hit'] for x,y in zip(a,b)])),'paired_date_bootstrap95':list(map(float,np.quantile(samples,[.025,.975]))),'iterations':n}

def podium(rank,recs,cal):
 n=ordh=seth=0
 for z,g in recs:
  if not g['podium_valid']:continue
  p=rank.make_race_probabilities(z,cal);rel={int(idx):i for i,idx in enumerate(g['indices'])}
  truth=(rel[g['first']],rel[g['second']],rel[g['third']]);n+=1
  ordh+=int(tuple(p['ordered_pick'])==truth);seth+=int(set(p['unordered_pick'])==set(truth))
 return {'races_valid':n,'ordered_hits':ordh,'ordered_accuracy':ordh/n if n else None,'unordered_hits':seth,'unordered_accuracy':seth/n if n else None}

def file_sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for z in iter(lambda:f.read(1<<20),b''):h.update(z)
 return h.hexdigest()

def main():
 rank=module('v51_v2rank',FILES/'v51研究_v51_recovered_id_conditional_rank_v2.py');model=json.load(open(MODEL));dat=np.load(D/'v51_fouraxis_features_20261113.npz',allow_pickle=False)
 X=dat['X'];rids=dat['rids'];order=dat['rank'];status=dat['status'];years=dat['years'];nums=dat['nums'];extra=dat['feature'];
 c=sqlite3.connect(f'file:{DB}?mode=ro',uri=True);date=dict(c.execute('select race_id,race_date from annual_report_races'));c.close()
 rr={k:[{'date':v}] for k,v in date.items() if v is not None}
 group=rank.groups_for(rids,order,years,status,rr)
 training=[g for g in group if g['year']<=2024 and g['status']=='validated_result'];full25=sorted([g for g in group if g['year']==2025 and g['status']=='validated_result'],key=lambda g:(g['date'],g['race']));year26=sorted([g for g in group if g['year']==2026 and g['status']=='validated_result'],key=lambda g:(g['date'],g['race']))
 assert (len(training),len(full25),len(year26))==(5865,2925,2411)
 dates=sorted(set(g['date'] for g in full25));a=dates[int(.4*len(dates))];b=dates[int(.8*len(dates))];fit=[g for g in full25 if g['date']<a];search=[g for g in full25 if a<=g['date']<b];late=[g for g in full25 if g['date']>=b]
 log('cohort and date splits',len(training),len(fit),len(search),len(late),len(year26),a,b)
 assert (len(fit),len(search),len(late))==(1145,1186,594)
 mean=np.asarray(model['feature_mean']);scale=np.asarray(model['feature_scale']);W=np.asarray(model['stage_coefficients']);z=(X-mean)/scale;train_idx=np.concatenate([g['indices'] for g in training]);extr_mean=extra[train_idx].mean(axis=0);extr_sd=extra[train_idx].std(axis=0);extr_sd=np.where(extr_sd>1e-6,extr_sd,1);extr=(extra-extr_mean)/extr_sd
 st=[z@W[i] for i in range(3)];zero=np.zeros(14);base_cal=rank.calibrate(records(fit,st[0],extr,st,zero));log('calibrated baseline early only')
 base_middle,_=assess(rank,records(search,st[0],extr,st,zero),base_cal)
 base_late,_=assess(rank,records(late,st[0],extr,st,zero),base_cal)
 log('baseline scores middle',base_middle,'late',base_late)
 candidates={'official_baseline':zero}; diagnostics={};search_results={'official_baseline':base_middle};cals={'official_baseline':base_cal}
 for key,inds in GROUPS.items():
  flags={'opponent_class':[2,3],'running_style':[7],'jockey_condition':[10],'previous_weight':[13],'combined':[2,3,7,10,13]}[key]
  support=sum(np.count_nonzero(extra[train_idx,k]==0) for k in flags)
  if support<50 or not np.any(np.std(extra[train_idx][:,inds],axis=0)>1e-9):log('skip group',key,'support',support);continue
  for ridge in (.03,.10):
   label=f'{key}_ridge_{ridge}';log('TRAIN',label,'support',support)
   small,diag=train_residual(st[0],extr[:,inds],training,ridge);beta=np.zeros(14);beta[inds]=small
   candidates[label]=beta;diagnostics[label]=diag
   cals[label]=cal_candidate(rank,records(fit,st[0],extr,st,beta),base_cal)
   search_results[label],_=assess(rank,records(search,st[0],extr,st,beta),cals[label]);log('SEARCH',label,search_results[label])
 if len(candidates)==1:raise ValueError('No observed additional features in canonical DB')
 elig=[]
 for k,v in search_results.items():
  if v['winner_logloss']>base_middle['winner_logloss']+.02 or v['winner_brier']>base_middle['winner_brier']+.01 or v['ece_confidence']>base_middle['ece_confidence']+.025:continue
  elig.append((-v['top1_accuracy'],v['winner_logloss'],k))
 selected=min(elig)[2]
 log('selected 2025 middle',selected)
 baseconf,baseconf_rows=assess(rank,records(late,st[0],extr,st,zero),base_cal)
 newconf,newconf_rows=assess(rank,records(late,st[0],extr,st,candidates[selected]),cals[selected]);ci=boot_day(baseconf_rows,newconf_rows)
 passed=selected!='official_baseline' and ci['paired_date_bootstrap95'][0]>0 and newconf['winner_logloss']<baseconf['winner_logloss'] and newconf['winner_brier']<=baseconf['winner_brier']+.001 and newconf['ece_confidence']<=baseconf['ece_confidence']+.005
 log('2025 LATE baseline',baseconf,'candidate',newconf,'bootstrap',ci,'adopt?',passed)
 newcal_full=cal_candidate(rank,records(full25,st[0],extr,st,candidates[selected]),model['calibration'])
 all25_base,_=assess(rank,records(full25,st[0],extr,st,zero),model['calibration']);all25_new,_=assess(rank,records(full25,st[0],extr,st,candidates[selected]),newcal_full)
 audit_base,audit_base_rows=assess(rank,records(year26,st[0],extr,st,zero),model['calibration']);audit_new,audit_new_rows=assess(rank,records(year26,st[0],extr,st,candidates[selected]),newcal_full)
 log('2025 year descriptive',all25_base,all25_new)
 log('2026 fixed audit',audit_base,audit_new)
 if all25_base['top1_hits']!=719 or audit_base['top1_hits']!=603:raise ValueError('Official 31-feature baseline not reproduced')
 # Persist 2025 outcome before the podium calculation, which is more expensive.
 partial={'schema':'jra-v51-14-feature-REAL-observed-20261113-v1','source_database_sha256':model['canonical_db_sha256'],'source_overlay_sha256':model['review_overlay_sha256'],'original_31_features_frozen':True,'new_features':NAMES,'candidate_coefficients':{k:x.tolist() for k,x in candidates.items()},'feature_normalizer':{'mean':extr_mean.tolist(),'scale':extr_sd.tolist()},'fit_diagnostics':diagnostics,'train_races':len(training),'train_runners':len(train_idx),'split_2025':{'early':len(fit),'middle':len(search),'late':len(late),'early_until_exclusive':a,'middle_until_exclusive':b},'search_2025':search_results,'selected_candidate':selected,'confirmation_2025':{'baseline':baseconf,'candidate':newconf,'paired_bootstrap':ci,'strict_gate_passed':passed},'all_2025_in_sample_calibration':{'baseline':all25_base,'candidate':all25_new},'2026_frozen_audit':{'baseline':audit_base,'candidate':audit_new},'production_enabled':False,'current_race_result_bodyweight_used':False,'2026_used_for_selection':False,'historical_source_embargo_days':2}
 (D/'v51_14_real_train_rank_metrics.json').write_text(json.dumps(partial,ensure_ascii=False,indent=2)+'\n')
 for fname,A,B in [('2025_late',baseconf_rows,newconf_rows),('2026_audit',audit_base_rows,audit_new_rows)]:
  with (D/(fname+'_paired_race_metrics.csv')).open('w',newline='') as f:
   w=csv.writer(f);w.writerow(['race_id','date','baseline_hit','candidate_hit','baseline_logloss','candidate_logloss','baseline_brier','candidate_brier'])
   for x,y in zip(A,B):w.writerow([x['race_id'],x['date'],x['hit'],y['hit'],x['logloss'],y['logloss'],x['brier'],y['brier']])
 log('podium evaluation 2025 late / 2026')
 p25a=podium(rank,records(late,st[0],extr,st,zero),base_cal);p25b=podium(rank,records(late,st[0],extr,st,candidates[selected]),cals[selected]);p26a=podium(rank,records(year26,st[0],extr,st,zero),model['calibration']);p26b=podium(rank,records(year26,st[0],extr,st,candidates[selected]),newcal_full)
 partial['confirmation_2025']['podium_baseline']=p25a;partial['confirmation_2025']['podium_candidate']=p25b;partial['2026_frozen_audit']['podium_baseline']=p26a;partial['2026_frozen_audit']['podium_candidate']=p26b
 (D/'v51_14_real_train_rank_metrics.json').write_text(json.dumps(partial,ensure_ascii=False,indent=2)+'\n')
 cov=json.loads((D/'source_coverage.json').read_text());
 report=['# V51 追加14特徴量：正本実DBによる全期間再学習・2025年精度比較', '',f'2023〜24年: {len(training)}レース、2025年: 校正{len(fit)} / 選択{len(search)} / 未使用後期{len(late)}レース、2026監査{len(year26)}レース。','',f'**2025年中期に選択された候補:** `{selected}`','', '| 対象 | 現行V51 1着 | 新14特徴候補 1着 | 現行Log Loss | 候補Log Loss |','|---|---:|---:|---:|---:|']
 for name,o,p in [('2025後期（独立確認）',baseconf,newconf),('2025全期（同年内校正・参考）',all25_base,all25_new),('2026固定監査',audit_base,audit_new)]:report.append(f"| {name} | {o['top1_hits']}/{o['races']} ({100*o['top1_accuracy']:.2f}%) | {p['top1_hits']}/{p['races']} ({100*p['top1_accuracy']:.2f}%) | {o['winner_logloss']:.6f} | {p['winner_logloss']:.6f} |")
 report+=['',f"後期1着的中率差の開催日ブロック95%CI: **{100*ci['paired_date_bootstrap95'][0]:+.2f}～{100*ci['paired_date_bootstrap95'][1]:+.2f}ポイント**",f"**正式採用条件: {'合格' if passed else '不合格'}。正式V51は変更しない。**",'','| 対象 | 現行Brier | 候補Brier | 現行ECE | 候補ECE |','|---|---:|---:|---:|---:|']
 for name,o,p in [('2025後期',baseconf,newconf),('2026監査',audit_base,audit_new)]:report.append(f"| {name} | {o['winner_brier']:.6f} | {p['winner_brier']:.6f} | {o['ece_confidence']:.6f} | {p['ece_confidence']:.6f} |")
 report+=['','| 対象 | 現行 順序3頭 | 候補 順序3頭 | 現行 順不同3頭 | 候補 順不同3頭 |','|---|---:|---:|---:|---:|']
 for name,o,p in [('2025後期',p25a,p25b),('2026監査',p26a,p26b)]:report.append(f"| {name} | {o['ordered_hits']}/{o['races_valid']} | {p['ordered_hits']}/{p['races_valid']} | {o['unordered_hits']}/{o['races_valid']} | {p['unordered_hits']}/{p['races_valid']} |")
 report+=['','## 実データの特徴量入力可能数']
 for year,stats in sorted(cov['years'].items()):report.append(f"- {year}: {stats}")
 report+=['','**留保:** 過去JRA年度PDFの公開時刻は全件では検証されていないため、結果から2暦日経過した場合に過去履歴として使用した回顧比較。2026既閲覧データをモデル選択に使っていないが完全未見ではない。前走馬体重のみ使用。当該レース結果から当日馬体重を予測時点へ流用していない。正式31特徴量と2・3着係数は不変。']
 (D/'v51_14_real_train_2025_comparison.md').write_text('\n'.join(report)+'\n')
 (D/'research_14coefficients_not_production.json').write_text(json.dumps({'production_enabled':False,'name':selected,'coefficients':candidates[selected].tolist(),'mean':extr_mean.tolist(),'scale':extr_sd.tolist(),'calibration_research_only':newcal_full,'passed':passed},ensure_ascii=False,indent=2)+'\n')
 log('DONE')
 print('\n'.join(report),flush=True)
if __name__=='__main__':main()