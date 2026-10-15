"""EURASIA 2050 V4.4 — strictly chronological per-target model search.
Historic labels are observed-only. V4.1 is a frozen *reference/rollback*, not a
selection feature on overlapping training years. Held-out 2021–25 never tunes.
"""
from __future__ import annotations
import gc, json, time, warnings, math
from pathlib import Path
import numpy as np, pandas as pd, joblib, torch, optuna
from torch import nn
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor, HistGradientBoostingRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge, ElasticNet, HuberRegressor
from sklearn.svm import SVR
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from scipy.optimize import minimize
from eurasia_runtime import TARGETS, COUNTRIES, seed_all, write_json
from eurasia_v4 import load_world_v3
from eurasia_world_v42 import _dataset, _flat, _pred_fallback
optuna.logging.set_verbosity(optuna.logging.WARNING)

FAMILIES=['Ridge','ElasticNet','Huber','SVR','ExtraTrees','RandomForest','HistGB',
          'GradientBoost','CatBoost','MLP','GRU','LSTM','TCN']

def build_classic(kind,p,seed):
 if kind=='Ridge':return make_pipeline(StandardScaler(),Ridge(alpha=p.get('alpha',1.)))
 if kind=='ElasticNet':return make_pipeline(StandardScaler(),ElasticNet(alpha=p.get('alpha',.1),l1_ratio=p.get('l1_ratio',.4),max_iter=1600,random_state=seed))
 if kind=='Huber':return make_pipeline(StandardScaler(),HuberRegressor(epsilon=p.get('epsilon',1.5),alpha=p.get('alpha',.001),max_iter=220))
 if kind=='SVR':return make_pipeline(StandardScaler(),SVR(C=p.get('C',2.),epsilon=p.get('epsilon',.1),gamma='scale'))
 if kind=='ExtraTrees':return ExtraTreesRegressor(n_estimators=p.get('trees',110),min_samples_leaf=p.get('leaf',3),max_features=p.get('features',.8),n_jobs=2,random_state=seed)
 if kind=='RandomForest':return RandomForestRegressor(n_estimators=p.get('trees',110),min_samples_leaf=p.get('leaf',3),max_features=p.get('features',.8),n_jobs=2,random_state=seed)
 if kind=='HistGB':return HistGradientBoostingRegressor(max_iter=p.get('iterations',80),max_leaf_nodes=p.get('leaves',8),learning_rate=p.get('lr',.07),min_samples_leaf=8,l2_regularization=1.,random_state=seed)
 if kind=='GradientBoost':return GradientBoostingRegressor(n_estimators=p.get('iterations',80),learning_rate=p.get('lr',.06),max_depth=2,loss='huber',random_state=seed)
 if kind=='CatBoost':
  from catboost import CatBoostRegressor
  return CatBoostRegressor(iterations=p.get('iterations',100),depth=p.get('depth',3),learning_rate=p.get('lr',.06),l2_leaf_reg=4.,verbose=False,thread_count=2,random_seed=seed,allow_writing_files=False)
 raise ValueError(kind)

class TemporalNet(nn.Module):
 def __init__(self,kind,features,seq_len,width=32,dropout=.15):
  super().__init__();self.kind=kind;self.seq_len=seq_len
  if kind in ('GRU','LSTM'):
   self.net=(nn.GRU if kind=='GRU' else nn.LSTM)(features,width,batch_first=True)
   nout=width
  elif kind=='TCN':
   self.net=nn.Sequential(nn.Conv1d(features,width,3,padding=2,dilation=2),nn.GELU(),
                           nn.Conv1d(width,width,3,padding=1),nn.GELU(),nn.AdaptiveAvgPool1d(1))
   nout=width
  else:
   self.net=nn.Sequential(nn.Linear(features*seq_len,width),nn.GELU(),nn.Dropout(dropout),
                          nn.Linear(width,width),nn.GELU())
   nout=width
  self.head=nn.Sequential(nn.LayerNorm(nout),nn.Linear(nout,1))
 def forward(self,x):
  if self.kind in ('GRU','LSTM'): out=self.net(x)[0][:,-1]
  elif self.kind=='TCN':out=self.net(x.transpose(1,2)).squeeze(-1)
  else:out=self.net(x.reshape(len(x),-1))
  return self.head(out).flatten()

class TemporalEstimator:
 """Portable CPU estimator; neural architecture and tensors persisted by joblib."""
 def __init__(self,kind,p,seq_len,features,seed=42):
  self.kind=kind;self.params=dict(p);self.seq_len=int(seq_len);self.features=int(features);self.seed=seed;self.state=None
 def fit(self,X,y,years=None):
  X=np.asarray(X,np.float32).reshape(-1,self.seq_len,self.features);y=np.asarray(y,np.float32)
  torch.manual_seed(self.seed);torch.set_num_threads(min(3,max(1,torch.get_num_threads())))
  net=TemporalNet(self.kind,self.features,self.seq_len,self.params.get('width',32),self.params.get('dropout',.15))
  opt=torch.optim.AdamW(net.parameters(),lr=self.params.get('lr',.001),weight_decay=self.params.get('wd',.01))
  # Internal early stop uses only the training part of the outer chronological fold.
  if years is not None and len(np.unique(years))>=5:
   last=np.sort(np.unique(years))[-2:];val=np.isin(years,last)
  else:
   val=np.arange(len(X))>=max(int(.82*len(X)),1)
  if (~val).sum()<12 or val.sum()<3:val=np.zeros(len(X),bool)
  tx=torch.from_numpy(X);ty=torch.from_numpy(y);rng=np.random.default_rng(self.seed)
  best=1e30;best_state=None;bad=0
  for epoch in range(int(self.params.get('epochs',80))):
   net.train();indices=np.where(~val)[0];rng.shuffle(indices)
   for ids in np.array_split(indices,max(1,math.ceil(len(indices)/32))):
    if not len(ids):continue
    loss=(net(tx[ids])-ty[ids]).square().mean()
    opt.zero_grad();loss.backward();nn.utils.clip_grad_norm_(net.parameters(),1.);opt.step()
   net.eval()
   with torch.no_grad():
    v=float((net(tx[val])-ty[val]).square().mean()) if val.any() else float((net(tx)-ty).square().mean())
   if v<best-1e-5:
    best=v;best_state={k:q.detach().cpu().clone() for k,q in net.state_dict().items()};bad=0
   else:bad+=1
   if bad>=int(self.params.get('patience',12)):break
  net.load_state_dict(best_state);self.state={k:v.numpy() for k,v in net.state_dict().items()}
  return self
 def predict(self,X):
  if self.state is None:raise RuntimeError('Neural model not fitted')
  net=TemporalNet(self.kind,self.features,self.seq_len,self.params.get('width',32),self.params.get('dropout',.15))
  net.load_state_dict({k:torch.as_tensor(v) for k,v in self.state.items()});net.eval()
  X=np.asarray(X,np.float32).reshape(-1,self.seq_len,self.features)
  with torch.no_grad():return net(torch.as_tensor(X)).numpy().astype(np.float32)

def suggest(trial):
 kind=trial.suggest_categorical('kind',FAMILIES);p={}
 if kind in ['Ridge','ElasticNet','Huber']:p['alpha']=trial.suggest_float('alpha',.001,8.,log=True)
 if kind=='ElasticNet':p['l1_ratio']=trial.suggest_float('l1_ratio',.1,.9)
 if kind in ['SVR','Huber']:p['epsilon']=trial.suggest_float('epsilon',.04,.30) if kind=='SVR' else trial.suggest_float('epsilon',1.25,1.8)
 if kind=='SVR':p['C']=trial.suggest_float('C',.1,12.,log=True)
 if kind in ['ExtraTrees','RandomForest']:
  p['trees']=trial.suggest_categorical('trees',[60,110,180]);p['leaf']=trial.suggest_int('leaf',2,8);p['features']=trial.suggest_float('features',.45,1.)
 if kind in ['HistGB','GradientBoost','CatBoost']:
  p['iterations']=trial.suggest_categorical('iterations',[60,110,180]);p['lr']=trial.suggest_float('lr',.025,.12,log=True)
 if kind=='HistGB':p['leaves']=trial.suggest_int('leaves',4,15)
 if kind=='CatBoost':p['depth']=trial.suggest_int('depth',2,5)
 if kind in ['MLP','GRU','LSTM','TCN']:
  p['width']=trial.suggest_categorical('width',[16,32,48]);p['lr']=trial.suggest_float('lr',.0003,.003,log=True)
  p['wd']=trial.suggest_float('wd',.0001,.04,log=True);p['epochs']=trial.suggest_categorical('epochs',[55,85]);p['patience']=12;p['dropout']=.15
 return kind,p

def construct(kind,p,X,seed):
 return TemporalEstimator(kind,p,X.shape[1],X.shape[2],seed) if kind in ('MLP','GRU','LSTM','TCN') else build_classic(kind,p,seed)

def fit_one(kind,p,X,y,years,seed):
 est=construct(kind,p,X,seed)
 if isinstance(est,TemporalEstimator):est.fit(X,y,years)
 elif kind=='CatBoost' and years is not None and len(np.unique(years))>=5:
  # Determine tree count from ONLY earlier training years; refit all allowed
  # years at the selected iteration. Never peek into the outer validation/test.
  years=np.asarray(years); recent=np.sort(np.unique(years))[-2:]
  v=np.isin(years,recent); x=_flat(X)
  if np.count_nonzero(v)>=5 and np.count_nonzero(~v)>=25:
   with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    est.fit(x[~v],y[~v],eval_set=(x[v],y[v]),early_stopping_rounds=20,use_best_model=True)
   it=max(10,int(est.best_iteration_)+1)
   est=build_classic(kind,{**p,'iterations':it},seed)
  with warnings.catch_warnings():warnings.simplefilter('ignore');est.fit(x,y)
 else:
  with warnings.catch_warnings():warnings.simplefilter('ignore');est.fit(_flat(X),y)
 return est

def predict_one(est,X):
 return np.asarray(est.predict(X if isinstance(est,TemporalEstimator) else _flat(X)),np.float32).reshape(-1)

class PerTargetWorld44:
 def __init__(self,estimators,weights,seq_len):
  self.estimators=estimators;self.weights=weights;self.seq_len=seq_len
 def __call__(self,x):
  device=x.device if torch.is_tensor(x) else 'cpu';a=x.detach().cpu().numpy() if torch.is_tensor(x) else np.asarray(x)
  out=np.zeros((len(a),len(TARGETS)),np.float32)
  for j,experts in enumerate(self.estimators):
   for est,w in zip(experts,self.weights[j][1:]):
    if est is not None and w>1e-7:out[:,j]+=w*predict_one(est,a)
  return torch.as_tensor(out,device=device)
 def eval(self):return self

def _blend_weights(preds,y,limit=3):
  # First column = persistence; strictly nonnegative simplex, penalized toward low-variance mixtures.
  preds=np.asarray(preds,float);k=preds.shape[1];initial=np.array([1.]+[0.]*(k-1))
  if len(y)<5:return initial
  def fun(w):return float(np.mean((preds@w-y)**2)+.012*np.sum(w[1:]**2))
  r=minimize(fun,np.full(k,1/k),method='SLSQP',bounds=[(0,1)]*k,
   constraints={'type':'eq','fun':lambda w:w.sum()-1},options={'maxiter':130,'ftol':1e-10})
  return r.x if r.success and np.all(np.isfinite(r.x)) else initial

def train_world_v44(prep,out,fallback_dir,mode='FULL',trials_per_target=34,seed=42,progress_callback=None):
  out=Path(out);out.mkdir(parents=True,exist_ok=True)
  fallback_dir=Path(fallback_dir);safe,safe_meta=load_world_v3(fallback_dir)
  old_state=json.loads((fallback_dir/'scalers_and_state.json').read_text())
  if old_state.get('countries')!=prep.meta().get('countries') or old_state.get('sequence_length')!=prep.seq_len:
   raise ValueError('V4.1 fallback scaler mismatch — cannot proceed')
  X,Y,M,YR,CTR=_dataset(prep); assert X.shape[1]==5 and YR.max()==2024
  # Folds begin in 2015 because Prepared normalizer was fitted on history <=2014.
  fold_ranges=[(2015,2015),(2016,2016)]
  val=(YR>=2017)&(YR<=2019);test=(YR>=2020)&(YR<=2024)
  oldtest=_pred_fallback(safe,X[test]); selections=[];trials=[];cvrows=[];hold=[];estimators=[];weights=[]
  full_y=Y[test];fullmask=M[test];allpred=np.zeros_like(full_y)
  for j,target in enumerate(TARGETS):
   start=time.monotonic();seed_all(seed+j*101)
   def objective(trial):
    kind,p=suggest(trial);values=[]
    for fold,(a,b) in enumerate(fold_ranges):
     it=(YR<a)&M[:,j];iv=(YR>=a)&(YR<=b)&M[:,j]
     if it.sum()<25 or iv.sum()<5:return 1e5
     try:
      model=fit_one(kind,p,X[it],Y[it,j],YR[it],seed+j*107+trial.number*3+fold)
      err=float(np.mean((predict_one(model,X[iv])-Y[iv,j])**2))
      if not np.isfinite(err):return 1e5
      values.append(err)
      # MedianPruner was previously configured but never received reports.
      # These two chronological folds are BOTH inside the model-selection data.
      trial.report(float(np.mean(values)),step=fold)
      if trial.should_prune():raise optuna.TrialPruned()
     except optuna.TrialPruned:raise
     except Exception as e:
      trial.set_user_attr('failed',str(e)[:160]);return 1e5
    trial.set_user_attr('fold_scores',values)
    return float(np.mean(values)+.20*np.std(values)+.075*np.max(values))
   study=optuna.create_study(direction='minimize',sampler=optuna.samplers.TPESampler(seed=seed+j*77,n_startup_trials=13),
                             pruner=optuna.pruners.MedianPruner(n_startup_trials=10,n_warmup_steps=0,n_min_trials=5))
   ntr=int(trials_per_target if mode=='FULL' else 3)
   if mode=='FULL':
    for family in FAMILIES:study.enqueue_trial({'kind':family})
    ntr=max(ntr,len(FAMILIES))
   else:
    # SMOKE is a fast technical check, not a search over all architectures.
    for family in ['Ridge','ExtraTrees','CatBoost'][:ntr]:study.enqueue_trial({'kind':family})
   study.optimize(objective,n_trials=ntr,catch=(Exception,),show_progress_bar=False,
    callbacks=[lambda st,t,j=j: progress_callback((j+(t.number+1)/ntr)/8,f'{target} Optuna {t.number+1}/{ntr}') if progress_callback else None])
   complete=[t for t in study.trials if t.state==optuna.trial.TrialState.COMPLETE and t.value is not None and np.isfinite(t.value) and t.value<1e4]
   for t in study.trials:trials.append({'target':target,'trial':t.number,'score':t.value,'params':json.dumps(t.params,ensure_ascii=False),'state':t.state.name,'folds':json.dumps(t.user_attrs.get('fold_scores',[]))})
   # Diverse finalists; each family contributes at most one candidate. No picking on holdout.
   finalists=[];seen=set()
   for t in sorted(complete,key=lambda z:z.value):
    kind=t.params['kind']
    if kind not in seen:finalists.append(t);seen.add(kind)
    if len(finalists)==3:break
   vv=val&M[:,j]
   candidates=[];vp=[];scores=[]
   # Outer rolling-origin predictions: each of the three validation years is
   # scored by a model trained strictly on PRIOR years. Hyperparameters were fit only on 2015-16, normalizers only on <=2014.
   val_years=[(2017,2017),(2018,2019)]
   for t in finalists:
    kind=t.params['kind'];p={k:v for k,v in t.params.items() if k!='kind'}
    try:
     pred=np.full(int(vv.sum()),np.nan,dtype=float)
     for block_idx,(lo,hi) in enumerate(val_years):
      tr=(YR<lo)&M[:,j];held=(YR>=lo)&(YR<=hi)&M[:,j]
      if tr.sum()<25 or not held.any():raise RuntimeError('Insufficient observed chronological fold')
      model=fit_one(kind,p,X[tr],Y[tr,j],YR[tr],seed+j*131+t.number+block_idx)
      pred[np.isin(np.where(vv)[0],np.where(held)[0])]=predict_one(model,X[held])
     if not np.isfinite(pred).all():raise RuntimeError('OOF incomplete')
     candidates.append((kind,p,t.number));vp.append(pred)
     scores.append(float(np.mean((pred-Y[vv,j])**2)))
    except Exception as e:cvrows.append({'target':target,'candidate':kind,'error':str(e)[:200]})
   predmat=np.column_stack([np.zeros(vv.sum())]+vp)
   tuned=_blend_weights(predmat,Y[vv,j]) if vv.sum()>=12 else np.array([1.]+[0.]*len(vp))
   mse_tuned=float(np.mean((predmat@tuned-Y[vv,j])**2)) if vv.any() else float('inf')
   mse_persist=float(np.mean(Y[vv,j]**2)) if vv.any() else float('inf')
   annual=[]
   for yr in np.unique(YR[vv]):
    ii=YR[vv]==yr
    annual.append({'input_year':int(yr),'target_year':int(yr+1),
     'model_mse':float(np.mean((predmat[ii]@tuned-Y[vv,j][ii])**2)),
     'persistence_mse':float(np.mean(Y[vv,j][ii]**2))})
   wins=sum(q['model_mse']<q['persistence_mse'] for q in annual)
   max_worsening=max([q['model_mse']-q['persistence_mse'] for q in annual],default=0.)
   # A small aggregate gain cannot override universal annual degradation.
   selected=bool(mse_tuned+0.005<mse_persist and wins>=2 and
      max_worsening<=max(.06,.30*mse_persist) and tuned[1:].sum()>.05)
   if not selected:tuned=np.array([1.]+[0.]*len(vp))
   for q in annual:cvrows.append({'target':target,'candidate':'OUTER_YEAR',**q,
      'selected':selected,'OOF':True})
   fits=[]
   trainall=(YR<2020)&M[:,j]
   for idx,(kind,p,trial_id) in enumerate(candidates):
    if not selected or tuned[idx+1]<1e-7:fits.append(None);continue
    fits.append(fit_one(kind,p,X[trainall],Y[trainall,j],YR[trainall],seed+j*131+trial_id))
   estimators.append(fits);weights.append(tuned.tolist())
   for idx,(kind,p,tid) in enumerate(candidates):
    cvrows.append({'target':target,'candidate':kind,'trial':tid,'validation_mse':scores[idx],'weight':float(tuned[idx+1])})
   selection={'target':target,'selected':'+'.join(f'{x[0]}:{tuned[k+1]:.3f}' for k,x in enumerate(candidates) if tuned[k+1]>.01) if selected else 'PERSISTENCE',
    'weights':json.dumps(tuned.tolist()),'val_mse':mse_tuned if selected else mse_persist,
    'persistence_validation_mse':mse_persist,'validation_observations':int(vv.sum()),'outer_year_wins':wins,
    'max_annual_worsening':max_worsening,'selection_time_safe':True,
    'n_train_observed':int(trainall.sum()),'cv_best_mse':float(study.best_value) if complete else None,
    'elapsed_sec':round(time.monotonic()-start,2),'selection_uses_test':False,
    'v41_reference_excluded_from_selection':True}
   selections.append(selection)
   pd.DataFrame(selections).to_csv(out/'per_target_selection.csv',index=False)
   pd.DataFrame(trials).to_csv(out/'optuna_trials_per_target.csv',index=False)
   if progress_callback:progress_callback((j+1)/8,f'{target}: {selection["selected"]}')
   gc.collect()
   if torch.cuda.is_available():torch.cuda.empty_cache()
  final=PerTargetWorld44(estimators,weights,prep.seq_len)
  allpred=final(torch.from_numpy(X[test])).numpy()
  mse=float(np.square(allpred-full_y)[fullmask].mean());oldmse=float(np.square(oldtest-full_y)[fullmask].mean());pers=float(np.square(full_y)[fullmask].mean())
  for j,t in enumerate(TARGETS):
   mask=fullmask[:,j];den=max(1,int(mask.sum()))
   hold.append({'target':t,'n':int(mask.sum()),'v44_rmse_z':float(np.sqrt(((allpred[:,j]-full_y[:,j])[mask]**2).sum()/den)),
    'v41_rmse_z':float(np.sqrt(((oldtest[:,j]-full_y[:,j])[mask]**2).sum()/den)),
    'persistence_rmse_z':float(np.sqrt((full_y[:,j][mask]**2).sum()/den)),
    'v42_rmse_z':float('nan')})
  pd.DataFrame(hold).to_csv(out/'heldout_by_target.csv',index=False)
  test_years=YR[test]+1
  yearrows=[]
  for year in sorted(set(test_years)):
   where=(test_years==year);mm=fullmask[where]
   yearrows.append({'target_year':int(year),'v44_mse':float(np.square(allpred[where]-full_y[where])[mm].mean()),
                    'v41_mse':float(np.square(oldtest[where]-full_y[where])[mm].mean()),
                    'persistence_mse':float(np.square(full_y[where])[mm].mean())})
  pd.DataFrame(yearrows).to_csv(out/'yearly_mse.csv',index=False)
  without2021=(test_years!=2021);m2=fullmask[without2021]
  no21=float(np.square(allpred[without2021]-full_y[without2021])[m2].mean())
  no21base=float(np.square(full_y[without2021])[m2].mean())
  meta={'version':'V4.4','selected_kind':'strict_chronological_per_target_nonnegative_ensemble',
   'target_models':selections,'ensemble_test_mse':mse,'baseline_test_mse':pers,'v41_safe_test_mse':oldmse,
   'better_than_persistence_on_test':bool(mse<pers),'better_than_v41_on_test':bool(mse<oldmse),
   'test_mse_without_2021':no21,'persistence_mse_without_2021':no21base,
   'robust_without_2021':bool(no21<no21base),'num_optuna_trials':len(trials),'n_pruned_trials':int(sum(t['state']=='PRUNED' for t in trials)),'n_targets':8,
   'shrink_alpha':1.,'alpha_mode':'nonnegative_simplex_rolling_origin_2017_2020_labels',
   'selection_rule':'Pre-split normalization based on data <=2014. Optuna CV input 2015 and 2016; disjoint rolling-origin ensemble selection input 2017-19; NEVER tune on held-out input 2020-24 (targets 2021-25).',
   'v41_is_immutable_reference_not_leaky_validation_candidate':True,
   'no_claim_all_targets_improve':True,'selection_uses_test':False,
   'warning':'Single-year and long-horizon accuracy require separate independent checks; no claim of dominance'}
  write_json(meta,out/'world_metrics.json');write_json(prep.meta(),out/'scalers_and_state.json')
  joblib.dump({'estimators':estimators,'weights':weights,'seq_len':prep.seq_len},out/'per_target_estimators.joblib',compress=3)
  write_json({'seq_len':prep.seq_len,'fallback_dir':'v41_safe','weights':weights,'version':'V4.4'},out/'per_target_manifest.json')
  pd.DataFrame(trials).to_csv(out/'optuna_trials.csv',index=False)
  pd.DataFrame(cvrows).to_csv(out/'candidate_models.csv',index=False)
  pd.DataFrame(hold).rename(columns={'v44_rmse_z':'model_rmse_z'}).to_csv(out/'target_weights.csv',index=False)
  pd.DataFrame({'target_year':test_years,'country':[COUNTRIES[i] for i in CTR[test]]}|{
   key+'_actual_delta_z':full_y[:,j] for j,key in enumerate(TARGETS)}|{
   key+'_model_delta_z':allpred[:,j] for j,key in enumerate(TARGETS)}|{
   key+'_observed':fullmask[:,j].astype(int) for j,key in enumerate(TARGETS)}).to_csv(out/'heldout_predictions.csv',index=False)
  return [final],meta

def load_world_v44(folder):
 folder=Path(folder);meta=json.loads((folder/'world_metrics.json').read_text())
 if meta['version']!='V4.4':raise ValueError('Requires V4.4 weights')
 p=joblib.load(folder/'per_target_estimators.joblib')
 if p['seq_len']!=5:raise ValueError('V4.4 requires seq_len=5')
 return [PerTargetWorld44(p['estimators'],p['weights'],p['seq_len'])],meta
