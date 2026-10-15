"""Eurasia V4.5 Stage2: short-panel global forecasting, chronological OOF selection.
Separate country and target categorical covariates; no synthetic historic targets.
No artificial weight limits on persistence; 2021-2025 diagnostics are NOT a pristine holdout.
"""
from __future__ import annotations
import gc, json, warnings
from pathlib import Path
import numpy as np, pandas as pd, joblib, torch
from catboost import CatBoostRegressor
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from scipy.optimize import minimize
from eurasia_runtime import TARGETS, COUNTRIES, FEATURES, write_json
from eurasia_world_v42 import _dataset

NUM_NAMES=[f'last_{f}' for f in FEATURES]+[f'mask_{f}' for f in FEATURES]+[f'prev_{f}' for f in TARGETS]+[f'lagdiff_{f}' for f in TARGETS]+['graph_share','source_confidence']
CAT=['country','target']

def panel_features(X,countries,years,metric_indices,observations=None):
    X=np.asarray(X,np.float32);countries=np.asarray(countries,dtype=int)
    years=np.asarray(years,dtype=int);metric_indices=np.asarray(metric_indices,dtype=int)
    if X.ndim!=3 or X.shape[1]!=5 or len(X)!=len(countries) or len(X)!=len(years) or len(X)!=len(metric_indices):
        raise ValueError('Requires 5-year sequences and explicit country/metric identity')
    # make_step schema: first |FEATURES| values are z; next |FEATURES| are observed masks.
    nf=len(FEATURES);tidx=[FEATURES.index(t) for t in TARGETS]
    last=X[:,-1,:];prev=X[:,-2,:]
    numeric=np.column_stack([last[:,:nf],last[:,nf:2*nf],prev[:,tidx],last[:,tidx]-prev[:,tidx],
        last[:,-2],last[:,-1]]).astype(np.float32)
    rows=pd.DataFrame(numeric,columns=NUM_NAMES)
    rows['country']=[COUNTRIES[int(k)] for k in countries]
    rows['target']=[TARGETS[int(k)] for k in metric_indices]
    return rows

def long_observed(X,Y,M,years,countries,select):
    indices=[];metric=[]
    for j in range(len(TARGETS)):
        ix=np.where(np.asarray(select)&M[:,j])[0]
        indices.extend(ix.tolist());metric.extend([j]*len(ix))
    ix=np.asarray(indices,int);metric=np.asarray(metric,int)
    if not len(ix):return pd.DataFrame(columns=NUM_NAMES+CAT),np.zeros(0),ix,metric
    df=panel_features(X[ix],countries[ix],years[ix],metric)
    return df,Y[ix,metric].astype(float),ix,metric

def _ridge(alpha):
    ct=ColumnTransformer([('numeric',StandardScaler(),NUM_NAMES),
      ('identity',OneHotEncoder(handle_unknown='ignore',sparse_output=False),CAT)],
      remainder='drop',sparse_threshold=0.)
    return Pipeline([('pre',ct),('reg',Ridge(alpha=alpha))])

def _cat(params,seed):
    return CatBoostRegressor(iterations=int(params.get('iterations',140)),depth=int(params.get('depth',3)),
       learning_rate=float(params.get('learning_rate',.045)),l2_leaf_reg=float(params.get('l2_leaf_reg',6.)),
       random_seed=int(seed),loss_function='RMSE',cat_features=CAT,thread_count=2,verbose=False,
       allow_writing_files=False)

def _fit(kind,params,X,y,seed,years=None):
    if len(X)<40:raise ValueError('Insufficient real historical target transitions')
    mod=_cat(params,seed) if kind=='catboost' else _ridge(float(params.get('alpha',10.)))
    if kind=='catboost' and years is not None and len(np.unique(years))>=5:
        yrs=np.asarray(years);held=np.isin(yrs,np.sort(np.unique(yrs))[-2:])
        if (~held).sum()>=40 and held.sum()>=8:
            mod.fit(X.iloc[~held],y[~held],eval_set=(X.iloc[held],y[held]),
                    early_stopping_rounds=25,use_best_model=True)
            best_iter=max(10,int(mod.best_iteration_)+1)
            mod=_cat({**params,'iterations':best_iter},seed)
    mod.fit(X,y)
    return mod

def _predict(mod,X):return np.asarray(mod.predict(X),float).reshape(-1)

def _weights(pred,y):
    # First column is persistence=0. No ungrounded mandatory complex-model quotas.
    pred=np.asarray(pred,dtype=float);y=np.asarray(y,dtype=float)
    k=pred.shape[1];inc=np.eye(k)[0]
    if len(y)<12:return inc
    def loss(w):return np.mean(np.square(pred@w-y)) + 0.002*np.sum(np.square(w[1:]))
    r=minimize(loss,np.full(k,1/k),method='SLSQP',bounds=[(0.,1.)]*k,
       constraints=[{'type':'eq','fun':lambda w:np.sum(w)-1}],
       options={'maxiter':300,'ftol':1e-11})
    return np.clip(r.x,0,1)/np.sum(np.clip(r.x,0,1)) if r.success else inc

class GlobalPanelWorld45:
    """Explicit country IDs for research; runtime supports exactly 8 countries in fixed order."""
    def __init__(self,catboost,ridge,weights):
        self.catboost=catboost;self.ridge=ridge;self.weights=np.asarray(weights,float)
        if self.weights.shape!=(len(TARGETS),3):raise ValueError('Weights shape [8,3] required')
    def predict_country(self,X,country,years):
        X=np.asarray(X,np.float32);country=np.asarray(country,int);years=np.asarray(years,int)
        if not (len(X)==len(country)==len(years)):raise ValueError('Country IDs and years are REQUIRED')
        output=np.zeros((len(X),len(TARGETS)),np.float32)
        for j in range(len(TARGETS)):
            d=panel_features(X,country,years,np.full(len(X),j))
            output[:,j]=self.weights[j,1]*_predict(self.catboost,d)+self.weights[j,2]*_predict(self.ridge,d)
        return output
    def __call__(self,X):
        # Simulation has the eight countries in explicit, invariant COUNTRIES order.
        a=X.detach().cpu().numpy() if torch.is_tensor(X) else np.asarray(X)
        if a.shape[0]!=len(COUNTRIES):
            raise ValueError('GlobalPanelWorld45 requires explicit country identities via predict_country for non-8 batches')
        # Runtime has no year field. No calendar-year predictor is used: only contemporaneous lagged state.
        country=np.arange(len(COUNTRIES));year=np.full(len(COUNTRIES),2024)
        out=self.predict_country(a,country,year)
        device=X.device if torch.is_tensor(X) else 'cpu'
        return torch.as_tensor(out,device=device)
    def eval(self):return self


def train_panel(prep,out,mode='FULL',seed=314159,progress_callback=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    X,Y,M,YR,CTR=_dataset(prep)
    if prep.seq_len!=5:raise ValueError('Sequence length 5 mandatory')
    if int(YR.max())>2024 or int(YR.min())<2004:raise AssertionError('unexpected historical years')
    # Feature normalizer in Prepared sees <=2014. Model selection only uses input years >=2015.
    folds=[2015,2016];oo_years=[2017,2018,2019]
    params=[{'iterations':90,'depth':2,'learning_rate':.05,'l2_leaf_reg':8},
            {'iterations':140,'depth':3,'learning_rate':.045,'l2_leaf_reg':6},
            {'iterations':190,'depth':3,'learning_rate':.03,'l2_leaf_reg':10},
            {'iterations':140,'depth':4,'learning_rate':.035,'l2_leaf_reg':12}]
    if mode=='SMOKE':params=params[:1]
    # Search hyperparameters ONLY in early chronological years.
    trialrows=[];best=None
    for idx,p in enumerate(params):
        scores=[]
        for fy in folds:
            trX,trY,train_ix,*_=long_observed(X,Y,M,YR,CTR,YR<fy)
            vaX,vaY,*_=long_observed(X,Y,M,YR,CTR,YR==fy)
            model=_fit('catboost',p,trX,trY,seed+idx,years=YR[train_ix])
            scores.append(float(np.mean(np.square(_predict(model,vaX)-vaY))))
        score=float(np.mean(scores)+.1*np.std(scores))
        trialrows.append({'trial':idx,'params':json.dumps(p),'score':score,'fold_2015':scores[0],'fold_2016':scores[1]})
        if best is None or score<best[0]:best=(score,p)
    pd.DataFrame(trialrows).to_csv(out/'early_tuning.csv',index=False)
    catpar=best[1];ridge_alpha=25.0
    # Each OOF year predicted by models trained STRICTLY BEFORE it. Missing labels excluded.
    predictions=[]
    for iy,fy in enumerate(oo_years):
        trX,trY,train_ix,*_=long_observed(X,Y,M,YR,CTR,YR<fy)
        vaX,vaY,ix,metric=long_observed(X,Y,M,YR,CTR,YR==fy)
        cat=_fit('catboost',catpar,trX,trY,seed+iy*11,years=YR[train_ix])
        ridge=_fit('ridge',{'alpha':ridge_alpha},trX,trY,seed+iy*11)
        cp=_predict(cat,vaX);rp=_predict(ridge,vaX)
        predictions.extend([{'input_year':int(fy),'target_year':int(fy+1),
          'country':COUNTRIES[int(CTR[k])],'target':TARGETS[int(m)],'metric_index':int(m),
          'actual_delta_z':float(y),'persistence':0.,'catboost':float(c), 'hier_ridge':float(r)}
          for k,m,y,c,r in zip(ix,metric,vaY,cp,rp)])
    oof=pd.DataFrame(predictions)
    oof.to_csv(out/'oof_2017_2019.csv',index=False)
    weights=[];selection=[]
    for j,name in enumerate(TARGETS):
        v=oof[oof.metric_index==j]
        y=v.actual_delta_z.to_numpy();p=np.column_stack([v.persistence,v.catboost,v.hier_ridge])
        w=_weights(p,y)
        mse=float(np.mean((p@w-y)**2));base=float(np.mean(y**2))
        # Leave nonselected fallback at persistence if difference is below practical threshold.
        # No forced complex-model quota; small OOF sample explicitly reported.
        if mse >= base-0.002:w=np.array([1.,0.,0.]);mse=base
        weights.append(w)
        selection.append({'target':name,'observed_oof':len(v),'weights':json.dumps(w.tolist()),
          'oof_mse':mse,'persistence_oof_mse':base,'selected':bool(w[0]<.999),'uses_test_years':False})
    pd.DataFrame(selection).to_csv(out/'selection_by_target.csv',index=False)
    # Freeze on input years <2020. Historical test 2021-2025 is used ONLY as descriptive reporting.
    trX,trY,train_ix,*_=long_observed(X,Y,M,YR,CTR,YR<2020)
    cat=_fit('catboost',catpar,trX,trY,seed+777,years=YR[train_ix])
    ridge=_fit('ridge',{'alpha':ridge_alpha},trX,trY,seed+777)
    wm=GlobalPanelWorld45(cat,ridge,weights)
    test=(YR>=2020)&(YR<=2024)
    pred=wm.predict_country(X[test],CTR[test],YR[test])
    truth=Y[test];mask=M[test]
    error=float(np.square(pred-truth)[mask].mean());persistence=float(np.square(truth)[mask].mean())
    sample_year=YR[test]+1
    yearrows=[]
    for year in sorted(np.unique(sample_year)):
        iy=sample_year==year;v=mask[iy]
        yearrows.append({'target_year':int(year),'mse':float(np.square(pred[iy]-truth[iy])[v].mean()),
             'persistence_mse':float(np.square(truth[iy])[v].mean())})
    pd.DataFrame(yearrows).to_csv(out/'historical_test_by_year.csv',index=False)
    # Empirical absolute residual uncertainty from OOF only; not conformal coverage guarantee.
    q={}
    for j,t in enumerate(TARGETS):
        v=oof[oof.metric_index==j];w=np.asarray(weights[j]);res=v.actual_delta_z-v[['persistence','catboost','hier_ridge']].to_numpy()@w
        q[t]=float(np.quantile(np.abs(res),.8)) if len(res)>0 else None
    joblib.dump(wm,out/'global_panel_world.joblib',compress=3)
    meta={'version':'V4.5-stage2','model':'global_catboost_plus_hierarchical_ridge',
     'target_models':selection,'test_mse':error,'persistence_test_mse':persistence,
     'test_is_not_pristine':True,'test_target_years':[2021,2022,2023,2024,2025],
     'oof_input_years':oo_years,'tuning_input_years':folds,
     'ooof_abs_error_q80_diagnostic_only':q,
     'no_forced_persistence_weight_limit':True,
     'runtime_batch_contract':'exactly 8 countries ordered RUS BLR KAZ KGZ UZB TJK TKM ARM',
     'runtime_calendar_predictor_used':False,
     'limitation':'No calibrated long-horizon uncertainty or trained Bayesian state-space component; do not claim 2050 forecasts verified.'}
    write_json(meta,out/'stage2_manifest.json')
    return wm,meta


def load_panel(folder):
    p=Path(folder);o=joblib.load(p/'global_panel_world.joblib')
    meta=json.loads((p/'stage2_manifest.json').read_text())
    if meta['version']!='V4.5-stage2':raise ValueError('V4.5 stage 2 required')
    return [o],meta
