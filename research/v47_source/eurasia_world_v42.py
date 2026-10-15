"""Eurasia 2050 V4.2 -- per-target chronological hyperparameter search.
Original V4.1 saved weights remain immutable, physically packaged as fallback.
No missing historical targets are fed into estimators. Test years are evaluation only.
"""
import gc, json, time, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
import torch
import optuna
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor, HistGradientBoostingRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge, ElasticNet
from sklearn.svm import SVR
from sklearn.neural_network import MLPRegressor
from eurasia_runtime import TARGETS,COUNTRIES,seed_all,write_json
from eurasia_v4 import load_world_v3
optuna.logging.set_verbosity(optuna.logging.WARNING)

CANDIDATES=['Ridge','ElasticNet','ExtraTrees','RandomForest','HistGB','GradientBoost','SVR','MLP','CatBoost']

def _one_model(kind,params,seed):
 if kind=='Ridge':return Ridge(alpha=params['alpha'])
 if kind=='ElasticNet':return ElasticNet(alpha=params['alpha'],l1_ratio=params['l1_ratio'],max_iter=1000,random_state=seed)
 if kind=='ExtraTrees':return ExtraTreesRegressor(n_estimators=params['n_estimators'],min_samples_leaf=params['leaf'],max_features=params['features'],n_jobs=2,random_state=seed)
 if kind=='RandomForest':return RandomForestRegressor(n_estimators=params['n_estimators'],min_samples_leaf=params['leaf'],max_features=params['features'],n_jobs=2,random_state=seed)
 if kind=='HistGB':return HistGradientBoostingRegressor(max_iter=params['iterations'],max_leaf_nodes=params['leaves'],learning_rate=params['learning_rate'],min_samples_leaf=8,l2_regularization=.1,random_state=seed)
 if kind=='GradientBoost':return GradientBoostingRegressor(n_estimators=params['iterations'],learning_rate=params['learning_rate'],max_depth=2,loss='huber',random_state=seed)
 if kind=='SVR':return SVR(C=params['C'],epsilon=params['epsilon'],gamma='scale')
 if kind=='MLP':return MLPRegressor(hidden_layer_sizes=(params['width'],),alpha=params['alpha'],learning_rate_init=.001,max_iter=180,early_stopping=False,random_state=seed)
 if kind=='CatBoost':
  from catboost import CatBoostRegressor
  return CatBoostRegressor(iterations=params['iterations'],depth=params['depth'],learning_rate=params['learning_rate'],loss_function='RMSE',thread_count=2,verbose=False,random_seed=seed)
 raise ValueError(kind)

def _suggest(t):
 kind=t.suggest_categorical('kind',CANDIDATES)
 p={}
 if kind in ('Ridge','ElasticNet','MLP'):p['alpha']=t.suggest_float('alpha',.001,10.,log=True)
 if kind=='ElasticNet':p['l1_ratio']=t.suggest_float('l1_ratio',.05,.9)
 if kind in ('ExtraTrees','RandomForest'):
  p.update(n_estimators=t.suggest_categorical('n_estimators',[50,100,160]),leaf=t.suggest_int('leaf',2,7),features=t.suggest_float('features',.5,1.))
 if kind in ('HistGB','GradientBoost','CatBoost'):
  p.update(iterations=t.suggest_categorical('iterations',[60,100,150]),learning_rate=t.suggest_float('learning_rate',.025,.15,log=True))
 if kind=='HistGB':p['leaves']=t.suggest_int('leaves',4,12)
 if kind=='CatBoost':p['depth']=t.suggest_int('depth',2,5)
 if kind=='SVR':p.update(C=t.suggest_float('C',.1,15,log=True),epsilon=t.suggest_float('epsilon',.02,.35))
 if kind=='MLP':p['width']=t.suggest_categorical('width',[16,32,64])
 return kind,p

def _dataset(prep):
 # padded features/masks are inputs, never interpreted as observed missing output labels
 hist=np.stack([s[0] for s in prep.samples]).astype(np.float32)
 y=np.stack([s[1] for s in prep.samples]).astype(np.float32)
 m=np.stack([s[2] for s in prep.samples]).astype(bool)
 years=np.array([s[3] for s in prep.samples]);countries=np.array([s[4] for s in prep.samples])
 return hist,y,m,years,countries

def _flat(x):return np.asarray(x).reshape(len(x),-1)

def _pred_fallback(fallback_models,x):
 if not fallback_models:return np.zeros((len(x),len(TARGETS)),np.float32)
 t=torch.from_numpy(np.asarray(x,dtype=np.float32))
 with torch.no_grad():return np.stack([net(t).detach().cpu().numpy() for net in fallback_models]).mean(0).astype(np.float32)

class PerTargetWorld:
 """Single adapter returning [batch,8] for unchanged MARL game API."""
 def __init__(self,estimators,alpha,fallback_models,seq_len):
  self.estimators=estimators;self.alpha=np.array(alpha,dtype=np.float32)
  self.fallback_models=fallback_models;self.seq_len=int(seq_len)
 def __call__(self,x):
  if torch.is_tensor(x):
   device=x.device;arr=x.detach().cpu().numpy()
  else:device='cpu';arr=np.asarray(x)
  old=_pred_fallback(self.fallback_models,arr)
  raw=_flat(arr);prediction=old.copy()
  for i,m in enumerate(self.estimators):
   if m is not None and self.alpha[i]>1e-6:
    now=np.asarray(m.predict(raw),np.float32).reshape(-1)
    prediction[:,i]=(1-self.alpha[i])*old[:,i]+self.alpha[i]*now
  return torch.from_numpy(prediction).to(device)
 def eval(self):return self

def train_world_v42(prep,out,fallback_dir,mode='FULL',trials_per_target=18,seed=42,progress_callback=None):
 out=Path(out);out.mkdir(exist_ok=True,parents=True)
 fallback_dir=Path(fallback_dir);old,old_report=load_world_v3(fallback_dir)
 # Baseline V4.1 is fixed: its normalizers and historic-country identities must match.
 baseline_state=json.loads((fallback_dir/'scalers_and_state.json').read_text())
 current=prep.meta()
 if baseline_state.get('countries')!=current.get('countries') or baseline_state.get('sequence_length')!=current.get('sequence_length'):
  raise ValueError('Stored V4.1 baseline uses incompatible countries or lag length')
 if abs(len(old)-3)>0:raise RuntimeError('V4.1 fallback must contain three trained models')
 x,y,mask,year,country=_dataset(prep)
 # Never fit on test >=2020 input years (target years >=2021)
 assert year.max()<=2024 and np.all(year[mask.any(1)]<=2024)
 rng=np.random.default_rng(seed)
 estimators=[None]*len(TARGETS);alphas=np.zeros(len(TARGETS),np.float32)
 rows=[];trial_rows=[];fold_rows=[]
 # Validation splits for tuning: prior years < min(test_year); 2 chronological folds
 folds=[(2012,2014),(2015,2017)]
 # Separate 2018-2019 selection for fallback mixing; untouched test 2020-2024
 val=(year>=2018)&(year<=2019)
 test=(year>=2020)&(year<=2024)
 old_val=_pred_fallback(old,x[val]);old_test=_pred_fallback(old,x[test])
 hold_rows=[];started=time.monotonic()
 for j,target in enumerate(TARGETS):
  seed_all(seed+j*43);t0=time.monotonic()
  def objective(t):
   kind,params=_suggest(t);scores=[]
   for f,(low,high) in enumerate(folds):
    train=(year<low)&mask[:,j];valid=(year>=low)&(year<=high)&mask[:,j]
    if train.sum()<30 or valid.sum()<4:continue
    try:
     model=_one_model(kind,params,seed+j*121+t.number)
     with warnings.catch_warnings():
      warnings.simplefilter('ignore');model.fit(_flat(x[train]),y[train,j])
     scores.append(float(np.mean((model.predict(_flat(x[valid]))-y[valid,j])**2)))
    except Exception:return 1e6
   t.set_user_attr('n_valid_folds',len(scores))
   return float(np.mean(scores)) if len(scores)==len(folds) else 1e5
  # Optuna journal is written after each target, so earlier targets are retained if a later one fails
  study=optuna.create_study(direction='minimize',sampler=optuna.samplers.TPESampler(seed=seed+j*51))
  ntr=int(trials_per_target if mode=='FULL' else 2)
  if ntr>=len(CANDIDATES):
   for algorithm in CANDIDATES:study.enqueue_trial({'kind':algorithm})
  def callback(study,trial):
   if progress_callback:progress_callback((j+(trial.number+1)/ntr)/len(TARGETS),
        f'{target}: Optuna {trial.number+1}/{ntr}')
  study.optimize(objective,n_trials=ntr,callbacks=[callback],catch=(Exception,),show_progress_bar=False)
  for trial in study.trials:trial_rows.append({'target':target,'trial':trial.number,'score':trial.value,'parameters':json.dumps(trial.params,ensure_ascii=False),'state':str(trial.state)})
  pbest=study.best_trial.params;kind=pbest['kind'];params={k:v for k,v in pbest.items() if k!='kind'}
  train=(year<2018)&mask[:,j];v=val&mask[:,j]
  try:
   trialmodel=_one_model(kind,params,seed+999+j)
   with warnings.catch_warnings():warnings.simplefilter('ignore');trialmodel.fit(_flat(x[train]),y[train,j])
   estimated=trialmodel.predict(_flat(x[val]))
  except Exception:
   kind='V4.1_ONLY';estimated=np.zeros(len(old_val))
  # pick between persistence, V4.1 exact saved model, and new per-target proposal
  old_pred=old_val[:,j];yy=y[val,j];mm=mask[val,j]
  candidates=[('V4.1_SAFE',0.0,old_pred),('PERSISTENCE',-1.,np.zeros_like(old_pred))]
  if kind!='V4.1_ONLY':
   for alpha in [.25,.5,.75,1.0]:
    candidates.append((kind,alpha,(1-alpha)*old_pred+alpha*estimated))
  scores=[(float(np.mean((p[mm]-yy[mm])**2)),kind2,alpha2) for kind2,alpha2,p in candidates]
  bestscore,bestkind,alpha=min(scores,key=lambda a:a[0])
  # Persistence is explicit per-target fallback; no learned target is fitted for it
  if bestkind=='PERSISTENCE':
   # substitute a zero-predictor with a tiny fitted dummy to ensure inference consistently uses zero
   from sklearn.dummy import DummyRegressor
   model=DummyRegressor(strategy='constant',constant=0.0).fit(np.zeros((1,x.shape[1]*x.shape[2])),[0.])
   alpha=1.
  elif bestkind=='V4.1_SAFE':model=None;alpha=0.
  else:
   tr=(year<2020)&mask[:,j]
   model=_one_model(kind,params,seed+999+j)
   with warnings.catch_warnings():warnings.simplefilter('ignore');model.fit(_flat(x[tr]),y[tr,j])
  estimators[j]=model;alphas[j]=float(alpha)
  rows.append({'target':target,'selected':bestkind,'alpha_new':float(alpha),
    'validation_mse':bestscore,'fallback_v41_validation_mse':float(np.mean((old_pred[mm]-yy[mm])**2)),
    'persistence_validation_mse':float(np.mean(yy[mm]**2)),
    'cv_best_mse':float(study.best_value),'n_train_observed':int(np.sum((year<2020)&mask[:,j])),
    'n_val_observed':int(np.sum(mm)),'elapsed_sec':round(time.monotonic()-t0,2),
    'selection_uses_test':False})
  pd.DataFrame(rows).to_csv(out/'per_target_selection.csv',index=False)
  pd.DataFrame(trial_rows).to_csv(out/'optuna_trials_per_target.csv',index=False)
  if progress_callback:progress_callback((j+1)/len(TARGETS),f'{target}: выбрано {bestkind}, α={alpha}')
  gc.collect()
  if torch.cuda.is_available():torch.cuda.empty_cache()
 final=PerTargetWorld(estimators,alphas,old,prep.seq_len)
 testpred=final(torch.from_numpy(x[test])).numpy();true=y[test];mk=mask[test]
 testmse=float(np.square(testpred-true)[mk].mean())
 oldmse=float(np.square(old_test-true)[mk].mean())
 persist=float(np.square(true)[mk].mean())
 for j,key in enumerate(TARGETS):
  seen=mk[:,j]
  hold_rows.append({'target':key,'n':int(seen.sum()),
   'v42_rmse_z':float(np.sqrt(np.square(testpred[seen,j]-true[seen,j]).mean())) if seen.any() else None,
   'v41_rmse_z':float(np.sqrt(np.square(old_test[seen,j]-true[seen,j]).mean())) if seen.any() else None,
   'persistence_rmse_z':float(np.sqrt(np.square(true[seen,j]).mean())) if seen.any() else None})
 pd.DataFrame(hold_rows).to_csv(out/'heldout_by_target.csv',index=False)
 meta={'version':'V4.2','selected_kind':'per_target_composite','target_models':rows,
  'ensemble_test_mse':testmse,'baseline_test_mse':persist,'v41_safe_test_mse':oldmse,
  'better_than_persistence_on_test':testmse<persist,'better_than_v41_on_test':testmse<oldmse,
  'num_optuna_trials':len(trial_rows),'n_targets':8,'alpha_mode':'individual_validation_2018_2019',
  'shrink_alpha':1.0,'selection_rule':'CV folds: train to 2011/test 2012–14; train to 2014/test 2015–17; blend selection 2018–19; true test 2020–24 input years',
  'note':'V4.1 saved model is immutable fallback; no test-based model selection. Model effects remain structural assumptions.'}
 write_json(meta,out/'world_metrics.json');write_json(prep.meta(),out/'scalers_and_state.json')
 joblib.dump(estimators,out/'per_target_estimators.joblib',compress=3)
 write_json({'alpha':alphas.tolist(),'fallback_dir':'v41_safe','seq_len':prep.seq_len},out/'per_target_manifest.json')
 pd.DataFrame(trial_rows).to_csv(out/'optuna_trials.csv',index=False)
 pd.DataFrame(rows).to_csv(out/'candidate_models.csv',index=False)
 # Preserve familiar diagnostics expected by older report components
 pd.DataFrame([{'target':z['target'],'model_rmse_z':z['v42_rmse_z'],'persistence_rmse_z':z['persistence_rmse_z'],'n':z['n']} for z in hold_rows]).to_csv(out/'target_weights.csv',index=False)
 pd.DataFrame({'target_year':year[test]+1,'country':[COUNTRIES[i] for i in country[test]]}|{
   key+'_actual_delta_z':true[:,j] for j,key in enumerate(TARGETS)}|{
   key+'_model_delta_z':testpred[:,j] for j,key in enumerate(TARGETS)}|{
   key+'_observed':mk[:,j].astype(int) for j,key in enumerate(TARGETS)}).to_csv(out/'heldout_predictions.csv',index=False)
 return [final],meta

def load_world_v42(folder):
 folder=Path(folder);meta=json.loads((folder/'world_metrics.json').read_text())
 if meta.get('version')!='V4.2':raise ValueError('Wrong World Model version')
 old,old_meta=load_world_v3(folder/'v41_safe')
 est=joblib.load(folder/'per_target_estimators.joblib')
 manifest=json.loads((folder/'per_target_manifest.json').read_text())
 return [PerTargetWorld(est,manifest['alpha'],old,manifest['seq_len'])],meta
