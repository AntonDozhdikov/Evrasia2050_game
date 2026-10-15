"""EURASIA 2050 V4. Honest model selection and bounded evolutionary game optimization.

History is never synthesized into the fitted targets. Validation 2015-2019 chooses architecture;
test 2020-2024 is evaluated once. Evolution works on synthetic game policy, not history.
This is *DGM-inspired constrained parameter evolution*, NOT a Darwin-Godel self-writing machine.
"""
from __future__ import annotations
import copy, json, math, time, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from torch import nn
from sklearn.linear_model import Ridge
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.multioutput import MultiOutputRegressor
from sklearn.dummy import DummyRegressor
import joblib
import optuna
from eurasia_runtime import (N,COUNTRIES,TARGETS,ACT_NAMES,WorldNet,Actor,Critic,Prepared,
   load_world as _legacy_load_world,train_mappo as _legacy_train_mappo,
   masked_mse,seed_all,write_json,simulate,eval_policies,EurasiaEnv)

optuna.logging.set_verbosity(optuna.logging.WARNING)

class ClassicalNet:
    """Readonly sklearn model: presents PyTorch tensor interface to numerical game."""
    def __init__(self,est,seq_len,dim): self.est=est;self.seq_len=seq_len;self.dim=dim
    def __call__(self,x):
        a=x.detach().cpu().numpy().reshape(len(x),-1)
        out=np.asarray(self.est.predict(a),np.float32)
        return torch.from_numpy(out)
    def eval(self):return self


def _masked_numpy(p,y,m):
    return float(((p-y)**2*m).sum()/max(m.sum(),1))

def _pred(model,x):
    with torch.no_grad():return model(x).detach().cpu().numpy().astype(np.float32)

def _fit_nn(kind,tr,va,params,seed,epochs,device):
    X,Y,M,_=tr; V,W,VM,_=va
    seed_all(seed)
    net=WorldNet(X.shape[-1],kind=kind,hidden=int(params.get('hidden',48)),seq_len=X.shape[1]).to(device)
    opt=torch.optim.AdamW(net.parameters(),lr=float(params.get('lr',0.001)),weight_decay=float(params.get('wd',0.02)))
    top=1e12;top_state=None;bad=0;steps=0
    for epoch in range(epochs):
        net.train();ids=torch.randperm(len(X))
        for chunk in ids.split(64):
            xb=X[chunk].to(device);yb=Y[chunk].to(device);mb=M[chunk].to(device)
            loss=masked_mse(net(xb),yb,mb)
            opt.zero_grad();loss.backward();nn.utils.clip_grad_norm_(net.parameters(),1.0);opt.step()
        net.eval()
        with torch.no_grad(): score=float(masked_mse(net(V.to(device)),W.to(device),VM.to(device)))
        steps=epoch+1
        if score<top-1e-5:
            top=score;bad=0;top_state={k:v.detach().cpu().clone() for k,v in net.state_dict().items()}
        else:bad+=1
        if bad>=int(params.get('patience',10)):break
    net.load_state_dict(top_state);net.cpu().eval()
    return net,top,steps

class ObservedTargetEstimator:
    """One model per target; NEVER train on missing labels or fabricate y=0."""
    def __init__(self, estimators):self.estimators=estimators
    def predict(self,X):
        X=np.asarray(X);n=len(X)
        return np.column_stack([est.predict(X) if est is not None else np.zeros(n) for est in self.estimators]).astype(np.float32)

def _fit_classic(kind,X,Y,M,params,seed):
    X=X.reshape(len(X),-1).numpy(); Y=Y.numpy(); M=M.numpy()
    models=[]
    for j in range(Y.shape[1]):
        keep=(M[:,j]>0.5)&np.isfinite(Y[:,j]);n=int(keep.sum())
        if n<12:
            models.append(None);continue # no fitted model for unsupported target
        if kind=='Ridge':est=Ridge(alpha=float(params.get('alpha',1.)),fit_intercept=True)
        elif kind=='ExtraTrees':est=ExtraTreesRegressor(n_estimators=int(params.get('n_estimators',80)),min_samples_leaf=int(params.get('min_samples_leaf',3)),max_features=float(params.get('max_features',.8)),n_jobs=2,random_state=seed+j)
        elif kind=='RandomForest':est=RandomForestRegressor(n_estimators=int(params.get('n_estimators',80)),min_samples_leaf=int(params.get('min_samples_leaf',3)),max_features=float(params.get('max_features',.8)),n_jobs=2,random_state=seed+j)
        elif kind=='HistGB':est=HistGradientBoostingRegressor(max_iter=int(params.get('max_iter',80)),learning_rate=float(params.get('learning_rate',0.05)),max_leaf_nodes=int(params.get('max_leaf_nodes',8)),l2_regularization=1.,min_samples_leaf=8,random_state=seed+j)
        elif kind=='CatBoost':
            from catboost import CatBoostRegressor
            est=CatBoostRegressor(iterations=int(params.get('iterations',90)),depth=int(params.get('depth',3)),learning_rate=float(params.get('learning_rate',0.06)),loss_function='RMSE',thread_count=2,verbose=False,random_seed=seed+j)
        else:raise ValueError(kind)
        est.fit(X[keep],Y[keep,j]);models.append(est)
    return ClassicalNet(ObservedTargetEstimator(models),X.shape[0] and int(params['_seq_len']),int(params['_step_dim']))

def _draw_params(trial,kind):
    if kind in ('GRU','LSTM','MLP','KAN'):
        return {'hidden':trial.suggest_categorical('hidden',[24,48,64]),'lr':trial.suggest_float('lr',3e-4,2e-3,log=True),'wd':trial.suggest_float('wd',1e-3,0.06,log=True),'patience':10}
    if kind=='Ridge':return {'alpha':trial.suggest_float('alpha',.03,100.,log=True)}
    if kind in ('ExtraTrees','RandomForest'):return {'n_estimators':trial.suggest_categorical('n_estimators',[64,96]),'min_samples_leaf':trial.suggest_int('min_samples_leaf',2,8),'max_features':trial.suggest_float('max_features',.5,1.)}
    if kind=='CatBoost':return {'iterations':trial.suggest_categorical('iterations',[70,110]),'depth':trial.suggest_int('depth',2,4),'learning_rate':trial.suggest_float('learning_rate',.03,.12,log=True)}
    if kind=='HistGB':return {'max_iter':trial.suggest_int('max_iter',40,120,step=40),'learning_rate':trial.suggest_float('learning_rate',.025,.12,log=True),'max_leaf_nodes':trial.suggest_int('max_leaf_nodes',5,12)}
    raise KeyError(kind)

def train_world_v3(prep,out,mode='FULL',seed=42,trials_per_kind=None,verbose=True,progress_callback=None):
    """Eight families; Optuna tuning train/validation only, positive ensemble weights; honest test."""
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    tr=prep.split(max(2003,2000+prep.seq_len-1),2014)
    va=prep.split(2015,2019);te=prep.split(2020,2024)
    X,Y,M,_=tr;V,W,VM,_=va;T,U,TM,_=te
    if float(M.sum())<80:raise ValueError('Observed target support insufficient')
    device='cuda' if torch.cuda.is_available() else 'cpu'
    kinds=['MLP','GRU','LSTM','KAN','Ridge','ExtraTrees','RandomForest','HistGB','CatBoost']
    trials_per_kind=int(trials_per_kind if trials_per_kind is not None else (5 if mode=='FULL' else 1))
    epochs=85 if mode=='FULL' else 3
    vals={}; fitted={};candidate_rows=[];trial_rows=[]
    total_work=len(kinds)*(trials_per_kind+1);completed=0
    for idx,kind in enumerate(kinds):
        if progress_callback:progress_callback(completed/total_work,f'{kind}: Optuna, {trials_per_kind} испытаний')
        def objective(trial):
            params=_draw_params(trial,kind)
            if kind in ('MLP','GRU','LSTM','KAN'):
                net,score,ep=_fit_nn(kind,tr,va,params,seed+101*idx+trial.number,epochs,device)
            else:
                net=_fit_classic(kind,X,Y,M,{**params,'_seq_len':X.shape[1],'_step_dim':X.shape[2]},seed+idx);score=_masked_numpy(_pred(net,V),W.numpy(),VM.numpy());ep=0
            trial.set_user_attr('epochs',ep)
            return score
        study=optuna.create_study(direction='minimize',sampler=optuna.samplers.TPESampler(seed=seed+idx*11),pruner=optuna.pruners.MedianPruner())
        def _optuna_event(study,trial):
            if progress_callback:progress_callback((idx*(trials_per_kind+1)+trial.number+1)/total_work,
                f'{kind}: Optuna {trial.number+1}/{trials_per_kind}')
        study.optimize(objective,n_trials=trials_per_kind,show_progress_bar=False,callbacks=[_optuna_event])
        params=dict(study.best_trial.params)
        if kind in ('MLP','GRU','LSTM','KAN'):
            net,score,ep=_fit_nn(kind,tr,va,params,seed+777+idx,epochs,device)
        else:
            net=_fit_classic(kind,X,Y,M,{**params,'_seq_len':X.shape[1],'_step_dim':X.shape[2]},seed+idx);score=_masked_numpy(_pred(net,V),W.numpy(),VM.numpy());ep=0
        fitted[kind]=net;vals[kind]=_pred(net,V)
        candidate_rows.append({'kind':kind,'validation_mse':score,'epochs':ep,'parameters':json.dumps(params,ensure_ascii=False),'family':'neural' if kind in kinds[:4] else 'classical'})
        for tt in study.trials:
            trial_rows.append({'kind':kind,'trial':tt.number,'value':tt.value,'parameters':json.dumps(tt.params,ensure_ascii=False),'state':str(tt.state)})
        completed=(idx+1)*(trials_per_kind+1)
        if progress_callback:progress_callback(completed/total_work,
            f'{kind}: проверен · MSE={score:.5f} · {idx+1}/{len(kinds)} алгоритмов')
        if verbose:print('World V4',kind,'val_mse',round(score,5),'trials',trials_per_kind)
    pd.DataFrame(candidate_rows).to_csv(out/'candidate_models.csv',index=False)
    pd.DataFrame(trial_rows).to_csv(out/'optuna_trials.csv',index=False)
    # Model selection by validation only, zero-residual persistence is explicitly included.
    base=_masked_numpy(np.zeros_like(W.numpy()),W.numpy(),VM.numpy())
    ranked=sorted(kinds,key=lambda k: _masked_numpy(vals[k],W.numpy(),VM.numpy()))
    combos=[([],[],'PERSISTENCE')]
    for kind in ranked:
        for alpha in (.15,.30,.50,.75,1.): combos.append(([kind],[alpha],kind))
    # nonnegative two-/three-model mixtures; include components from both different families
    neural=sorted(kinds[:4],key=lambda k:_masked_numpy(vals[k],W.numpy(),VM.numpy()))[:2]
    classic=sorted(kinds[4:],key=lambda k:_masked_numpy(vals[k],W.numpy(),VM.numpy()))[:2]
    for a in neural:
        for b in classic:
            for wa,wb in ((.25,.25),(.5,.5),(.65,.25),(.25,.65)):
                combos.append(([a,b],[wa,wb],f'{a}+{b}'))
    if len(neural)>0 and len(classic)>1:
        a=neural[0];b,c=classic[:2]
        for weight in (.15,.30): combos.append(([a,b,c],[weight,.35,.35],f'{a}+{b}+{c}'))
    def combo_pred(names,weights,inp=vals):
        p=np.zeros_like(W.numpy())
        for k,w in zip(names,weights):p+=float(w)*inp[k]
        return p
    scored=[(_masked_numpy(combo_pred(ns,ws),W.numpy(),VM.numpy()),ns,ws,label) for ns,ws,label in combos]
    # only accept improvement meaningful on validation, with 0.5% tolerance to reduce selection noise
    best=min(scored,key=lambda k:k[0]);chosen=best if best[0]<base*.995 else (base,[],[],'PERSISTENCE')
    _,names,weights,label=chosen
    # preserve diagnostics even if neutral/persistence selected. Weight models <= 3.
    predict_test={k:_pred(fitted[k],T) for k in names}
    p=combo_pred(names,weights,predict_test) if names else np.zeros_like(U.numpy())
    test_mse=_masked_numpy(p,U.numpy(),TM.numpy());base_test=_masked_numpy(np.zeros_like(U.numpy()),U.numpy(),TM.numpy())
    per=[]
    for j,key in enumerate(TARGETS):
        mm=TM.numpy()[:,j]>0
        per.append({'target':key,'n':int(mm.sum()),'model_rmse_z':float(np.sqrt(np.mean((p[mm,j]-U.numpy()[mm,j])**2))) if mm.any() else None,
           'persistence_rmse_z':float(np.sqrt(np.mean(U.numpy()[mm,j]**2))) if mm.any() else None})
    metadata=[];final=[]
    for j,kind in enumerate(names):
        model=fitted[kind];weight=weights[j]
        if kind in ('MLP','GRU','LSTM','KAN'):
            file=f'world_{j}.pt'
            torch.save({'weights':model.state_dict(),'kind':kind,'dim':X.shape[-1],
                'seq_len':X.shape[1],'hidden':model.hidden,'weight':weight,'version':4},out/file)
        else:
            file=f'world_{j}.joblib';joblib.dump(model.est,out/file,compress=3)
        metadata.append({'kind':kind,'file':file,'weight':weight});final.append(model)
    test_pred=pd.DataFrame({'target_year':[int(i+1) for i,j in te[3]],'country':[COUNTRIES[int(j)] for i,j in te[3]]})
    for k,key in enumerate(TARGETS):
        test_pred[key+'_actual_delta_z']=U.numpy()[:,k];test_pred[key+'_model_delta_z']=p[:,k];test_pred[key+'_observed']=TM.numpy()[:,k]
    test_pred.to_csv(out/'heldout_predictions.csv',index=False)
    report={'version':'V4','candidates':candidate_rows,'selected_kind':label,'selected_components':metadata,
        'shrink_alpha':1.0,'val_mse':float(chosen[0]),'baseline_val_mse':base,
        'ensemble_test_mse':test_mse,'baseline_test_mse':base_test,
        'better_than_persistence_on_test':bool(test_mse<base_test),
        'per_target':per,'ensemble_disagreement':float(np.std(np.stack(list(predict_test.values())),axis=0).mean()) if len(predict_test)>1 else 0.,
        'n_optuna_trials':len(trial_rows),'selection_rule':'validation 2015-2019, no test leakage; shrinkage and fallback persistence',
        'splits':{'train_target_years':'2005–2015' if prep.seq_len==5 else 'defined by seq_len',
           'validation_target_years':'2016–2020','test_target_years':'2021–2025'},
        'model_assessment':'validated_predictive' if test_mse<base_test else 'scenario_only_not_predictive',
        'note':'World ensemble output is already weighted; model weights do not establish causal action effects.'}
    write_json(report,out/'world_metrics.json');write_json(prep.meta(),out/'scalers_and_state.json')
    if verbose:print('WORLD V4 SELECTED:',label,'VAL',round(chosen[0],5),'TEST',round(test_mse,5),'baseline',round(base_test,5))
    return [WeightedNet(net,weights[i]*len(final)) for i,net in enumerate(final)],report

class WeightedNet:
    def __init__(self,net,weight):self.net=net;self.weight=float(weight)
    def __call__(self,x):return self.net(x)*self.weight
    def eval(self):return self

def load_world_v3(folder):
    folder=Path(folder);report=json.loads((folder/'world_metrics.json').read_text())
    if report.get('version')!='V4':raise ValueError('not V4 world checkpoint')
    arr=[]
    for item in report['selected_components']:
        path=folder/item['file']
        if path.suffix=='.pt':
            ck=torch.load(path,map_location='cpu',weights_only=True)
            net=WorldNet(ck['dim'],ck['kind'],hidden=ck['hidden'],seq_len=ck['seq_len'])
            net.load_state_dict(ck['weights']);net.eval()
        else:
            net=ClassicalNet(joblib.load(path),seq_len=5,dim=0)
        arr.append(WeightedNet(net,item['weight']*len(report['selected_components'])))
    return arr,report

class EvoActor(nn.Module):
    """Trusted bounded (8,6,3) action-logit offsets, shared trained PPO actor remains frozen."""
    def __init__(self,base,offset=None):
        super().__init__();self.base=base
        init=np.zeros((N,len(ACT_NAMES),3),np.float32) if offset is None else np.asarray(offset,np.float32)
        self.register_buffer('offset',torch.as_tensor(np.clip(init,-.8,.8)))
    def forward(self,obs):return self.base(obs)+self.offset.unsqueeze(0)

def _score_actor(prep,models,world_report,catalog,scenarios,actor,seeds,horizon=11):
    scores=[];div=[]
    for s in seeds:
        hist,rews=simulate(prep,models,world_report,actor,catalog,scenarios,seed=s,policy='MAPPO',horizon=horizon,sample_actions=False)
        scores.append(float(np.mean(rews))+.015*sum(x['projects']+x['agreements'] for x in hist))
        actions=np.asarray([r['actions'] for r in hist]);div.append(len(np.unique(actions[0],axis=0)))
    return float(np.mean(scores)),float(np.mean(div))

def evolve_policy_v3(prep,models,world_report,base,catalog,scenarios,out,mode='FULL',seed=42,verbose=True,progress_callback=None):
    """ES searches only a narrow policy offset. Validation and final evaluation use disjoint scenario seeds."""
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(seed)
    train_seeds=[seed+2101,seed+2149,seed+2243] if mode=='FULL' else [seed+2101]
    val_seeds=[seed+3103,seed+3203,seed+3301] if mode=='FULL' else [seed+3103]
    gens=10 if mode=='FULL' else 1;pop=8 if mode=='FULL' else 2
    horizon=11 if mode=='FULL' else 5
    current=np.zeros((N,len(ACT_NAMES),3),np.float32)
    best=-1e15;logs=[];sigma=.28
    neutral=[]
    for ss in val_seeds:
        _,rs=simulate(prep,models,world_report,base,catalog,scenarios,seed=ss,policy='NEUTRAL',horizon=horizon)
        neutral.append(float(np.mean(rs)))
    neutral_v=float(np.mean(neutral))
    baseline_tr,_=_score_actor(prep,models,world_report,catalog,scenarios,EvoActor(base,current),train_seeds,horizon)
    baseline_val,div0=_score_actor(prep,models,world_report,catalog,scenarios,EvoActor(base,current),val_seeds,horizon)
    best_val=baseline_val
    for gen in range(gens):
        pool=[current]
        for k in range(pop-1):
            mutation=rng.normal(0,sigma,current.shape).astype(np.float32)
            # bounded evolution: no architecture/code mutation, no alteration of historical datasets
            pool.append(np.clip(current+mutation,-.8,.8))
        evaluated=[]
        for k,candidate in enumerate(pool):
            a=EvoActor(base,candidate)
            raw,div=_score_actor(prep,models,world_report,catalog,scenarios,a,train_seeds,horizon)
            penalty=.04*float(np.mean(np.square(candidate)))
            fit=raw-penalty
            evaluated.append((fit,raw,div,k,candidate))
        evaluated.sort(key=lambda x:x[0],reverse=True)
        proposed=evaluated[0][4]
        vv,vdiv=_score_actor(prep,models,world_report,catalog,scenarios,EvoActor(base,proposed),val_seeds,horizon)
        accepted=bool(vv>best_val+0.025 and vdiv>=2.)
        if accepted:current=proposed.copy();best_val=vv
        sigma=max(.07,sigma*.83)
        logs.append({'generation':gen+1,'train_score':evaluated[0][1],'validation_score':vv,
            'accepted':accepted,'validation_best':best_val,'validation_neutral':neutral_v,
            'distinct_country_actions':vdiv,'mutation_std':sigma})
        if progress_callback:progress_callback((gen+1)/gens,f'Эволюция {gen+1}/{gens} · принято {sum(x["accepted"] for x in logs)}')
        if verbose:print('EVOLUTION',gen+1,'train',round(evaluated[0][1],2),'val',round(vv,2),'neutral',round(neutral_v,2),'accepted',accepted)
    actor=EvoActor(base,current).eval()
    pd.DataFrame(logs).to_csv(out/'evolution_history.csv',index=False)
    write_json({'kind':'bounded_evolution','mutation_only':'policy action-logit offsets',
        'max_abs_logit_shift':.8,'validation_seeds':val_seeds,'evolution_train_seeds':train_seeds,
        'neutral_validation_reward':neutral_v,'base_validation_reward':baseline_val,
        'evolved_validation_reward':best_val,'diversity_initial':div0,'accepted_mutations':sum(v['accepted'] for v in logs),
        'external_test_seed_policy':'use seeds >= seed + 5000','no_source_code_edits':True,
        'no_automatic_institutional_rule_mutation':True,'not_full_Darwin_Godel_machine':True},out/'evolution_manifest.json')
    return actor,logs

def train_marl_v3(prep,models,world_report,catalog,scenarios,out,mode='FULL',seed=42,updates=None,env_count=None,rollout=None,verbose=True,progress_callback=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    base,critic,log=_legacy_train_mappo(prep,models,world_report,catalog,scenarios,out,
       updates=updates or (115 if mode=='FULL' else 2),env_count=env_count or (8 if mode=='FULL' else 2),
       rollout=rollout or (16 if mode=='FULL' else 4),ppo_epochs=4 if mode=='FULL' else 1,seed=seed,verbose=verbose,
       progress_callback=(lambda f,d:progress_callback(.78*f,d)) if progress_callback else None)
    evolved,elog=evolve_policy_v3(prep,models,world_report,base,catalog,scenarios,out,mode=mode,seed=seed+70,verbose=verbose,
       progress_callback=(lambda f,d:progress_callback(.78+.22*f,d)) if progress_callback else None)
    ck=torch.load(out/'mappo.pt',map_location='cpu',weights_only=True)
    ck['version']=4;ck['algo']='MAPPO_CTDE_V4_BOUNDED_EVOLUTION';ck['evolution_offset']=evolved.offset.cpu()
    torch.save(ck,out/'mappo.pt')
    return evolved,critic,log,elog

def load_marl_v3(path):
    ck=torch.load(path,map_location='cpu',weights_only=True)
    if ck.get('version')!=4:raise ValueError('V4 MAPPO required')
    base=Actor(ck['obs_dim']);critic=Critic(ck['obs_dim'])
    base.load_state_dict(ck['actor']);critic.load_state_dict(ck['critic'])
    return EvoActor(base,ck['evolution_offset']).eval(),critic.eval()

def bounded_rule_evolution(prep,models,world_report,actor,catalog,scenarios,out,mode='FULL',seed=42,progress_callback=None):
    """Bounded, auditable DGM-*inspired* evolution of safe rule parameters.

    Evaluates proposed parameters on synthetic-game train seeds and separate validation seeds.
    Does NOT rewrite program code, history, geopolitical membership or hard legality rules.
    Accepted parameters require explicit human authorization before the public game uses them.
    """
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    bounds={'crisis_annual_probability':(.15,.60), 'institutional_cost_multiplier':(.85,1.15),
        'project_cost_multiplier':(.85,1.15), 'risk_aversion_multiplier':(.85,1.15)}
    baseline={'crisis_annual_probability':.34,'institutional_cost_multiplier':1.,
        'project_cost_multiplier':1.,'risk_aversion_multiplier':1.}
    rng=np.random.default_rng(seed)
    count=13 if mode=='FULL' else 2
    fit_seeds=[seed+101,seed+207] if mode=='FULL' else [seed+101]
    validate_seeds=[seed+421,seed+569] if mode=='FULL' else [seed+421]
    horizon=12 if mode=='FULL' else 5
    def evaluate(params,seeds):
        measures=[]
        for s in seeds:
            h,rs=simulate(prep,models,world_report,actor,catalog,scenarios,seed=s,policy='MAPPO',
                     horizon=horizon,sample_actions=False,rule_params=params)
            # Balanced utility: avoid selecting simply more reward via cost reduction, reward robustness/diversification.
            reward=float(np.mean(rs));div=float(np.mean([1-v['trade_concentration_mean'] for v in h]))
            shock=float(np.mean([bool(v['crises']) for v in h]))
            measure=reward/horizon + .5*div - .06*shock
            measures.append(measure)
        distance=sum(abs(params[k]-baseline[k])/(hi-lo) for k,(lo,hi) in bounds.items())
        return float(np.mean(measures)-.12*distance)
    baseline_train=evaluate(baseline,fit_seeds)
    baseline_val=evaluate(baseline,validate_seeds)
    best=baseline_val;chosen=baseline.copy()
    rows=[]
    for k in range(count):
        base=chosen if k and (k%2) else baseline
        proposal={key:float(np.clip(base[key]+rng.normal(0,(hi-lo)*.09),lo,hi))
             for key,(lo,hi) in bounds.items()}
        train_score=evaluate(proposal,fit_seeds)
        validation_score=evaluate(proposal,validate_seeds)
        valid=all(lo<=proposal[key]<=hi for key,(lo,hi) in bounds.items())
        accepted=bool(valid and train_score>baseline_train and validation_score>best+.005)
        if accepted:chosen=proposal.copy();best=validation_score
        if progress_callback:progress_callback((k+1)/count,f'Изменения правил {k+1}/{count}')
        rows.append({'proposal_id':f'R{k+1:03d}','parameters':json.dumps(proposal,ensure_ascii=False),
            'train_score':train_score,'validation_score':validation_score,'accepted_for_review':accepted,
            'within_bounds':valid,'approval_required':True,'source':'bounded_numeric_mutation'})
    pd.DataFrame(rows).to_csv(out/'rule_proposals.csv',index=False)
    write_json({'baseline':baseline,'bounds':bounds,'status':'VALIDATED_PROPOSAL_NEEDS_HUMAN_APPROVAL',
        'best_proposal_for_optional_game_use':chosen,'validation_baseline':baseline_val,
        'validation_selected':best,'validation_seeds':validate_seeds,'train_seeds':fit_seeds,
        'never_change':'historical data, identities, economy accounting, law/legality, geography, scenario provenance',
        'no_generated_code_execution':True,'not_full_dgm':True,'name':'Bounded Evolution / DGM-inspired'},out/'rule_evolution_contract.json')
    return rows

# ----------------------------------------------------------------------
# V4 comparison: heterogeneous sequential policy updates.
# This is a lightweight HAPPO-inspired comparator, NOT a full HAPPO implementation.
# The MAPPO baseline and honest label remain unchanged.
# ----------------------------------------------------------------------
def train_hetero_proxy_v4(prep,models,world_report,base,catalog,scenarios,out,mode='FULL',seed=42,progress_callback=None):
    from torch.distributions import Categorical
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(seed);torch.manual_seed(seed)
    base.eval();offset=torch.nn.Parameter(torch.zeros((N,len(ACT_NAMES),3),dtype=torch.float32))
    opt=torch.optim.Adam([offset],lr=0.015)
    logs=[];epochs=14 if mode=='FULL' else 2
    for ep in range(epochs):
        states=[];chosen=[];advantages=[]
        for k in range(2 if mode=='FULL' else 1):
            env=EurasiaEnv(prep,models,world_report,catalog,scenarios,seed+ep*101+k,horizon=9 if mode=='FULL' else 3)
            for _ in range(env.horizon):
                obs=torch.tensor(env.observe()[None],dtype=torch.float32)
                with torch.no_grad():
                    logits=base(obs)[0]+offset.detach()
                    pr=torch.softmax(logits,dim=-1).numpy()
                ac=np.asarray([[rng.choice(3,p=pr[i,j]) for j in range(len(ACT_NAMES))] for i in range(N)])
                _,rew,_,info=env.step(ac)
                states.append(obs);chosen.append(torch.tensor(ac,dtype=torch.long));advantages.append(torch.tensor(rew,dtype=torch.float32))
        st=torch.cat(states,dim=0);ac=torch.stack(chosen,dim=0);re=torch.stack(advantages,dim=0)
        # Agent-by-agent parameter updates and localized advantages: HAPPO-inspired proxy only.
        for i in rng.permutation(N):
            with torch.no_grad():ref=base(st)[:,i].detach()
            dist=Categorical(logits=ref+offset[i])
            logp=dist.log_prob(ac[:,i]).sum(-1)
            adv=re[:,i]-re[:,i].mean()
            loss=-(logp*adv).mean()+.05*(offset[i]**2).mean()-.005*dist.entropy().mean()
            opt.zero_grad();loss.backward();opt.step()
            with torch.no_grad():offset.clamp_(-.7,.7)
        logs.append({'epoch':ep+1,'mean_reward':float(re.mean()),'mean_abs_offset':float(offset.abs().mean().item()),'different_country_offsets':int(torch.unique(offset.detach().round(decimals=2),dim=0).shape[0])})
        if progress_callback:progress_callback((ep+1)/epochs,f'Гетерогенное обучение {ep+1}/{epochs}')
    actor=EvoActor(base,offset.detach().cpu().numpy());actor.eval()
    pd.DataFrame(logs).to_csv(out/'hetero_proxy_training.csv',index=False)
    torch.save({'policy_offsets':actor.offset.detach().cpu(),'version':4,'kind':'HAPPO_inspired_proxy_not_true_HAPPO'},out/'hetero_proxy.pt')
    return actor,pd.DataFrame(logs)


def map_elites_v4(prep,models,world_report,actor,catalog,scenarios,out,mode='FULL',seed=42,progress_callback=None):
    """Bounded 2D quality-diversity archive; descriptors are realized, not prescribed."""
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(seed);arc={};history=[]
    generations=7 if mode=='FULL' else 2
    population=7 if mode=='FULL' else 2
    for g in range(generations):
        for p in range(population):
            if arc and p%2==0:
                parent=list(arc.values())[int(rng.integers(len(arc)))]['offset']
            else:parent=np.zeros((N,len(ACT_NAMES),3),np.float32)
            trial=np.clip(parent+rng.normal(0,.22,parent.shape),-.65,.65).astype(np.float32)
            candidate=EvoActor(actor,trial)
            vals=[];projs=[];div=[];agreements=[]
            for k in range(2 if mode=='FULL' else 1):
                hist,r=simulate(prep,models,world_report,candidate,catalog,scenarios,seed=seed+4000+101*k,policy='MAPPO',horizon=10 if mode=='FULL' else 4,sample_actions=False)
                vals.append(float(np.mean(r)));projs.append(float(np.mean([h['projects'] for h in hist])));
                div.append(float(np.mean([1-h['trade_concentration_mean'] for h in hist])))
                agreements.append(float(np.mean([h['agreements'] for h in hist])))
            descriptor=(int(np.clip(np.mean(projs)*2,0,5)),int(np.clip(np.mean(div)*6,0,5)))
            fitness=float(np.mean(vals))+.025*np.mean(projs)+.015*np.mean(agreements)
            if descriptor not in arc or fitness>arc[descriptor]['fitness']:
                arc[descriptor]={'fitness':fitness,'projects_per_year':float(np.mean(projs)),
                     'agreements_per_year':float(np.mean(agreements)),'diversification':float(np.mean(div)),
                     'offset':trial.copy(),'generation':g+1}
            history.append({'generation':g+1,'candidate':p+1,'cell_project':descriptor[0],'cell_diversity':descriptor[1],
                'fitness':fitness,'projects_per_year':float(np.mean(projs)),'agreements_per_year':float(np.mean(agreements)),
                'filled_cells':len(arc)})
        if progress_callback:progress_callback((g+1)/generations,f'MAP-Elites {g+1}/{generations} · ниш {len(arc)}')
    best=max(arc.values(),key=lambda x:x['fitness'])
    pd.DataFrame(history).to_csv(out/'map_elites_trials.csv',index=False)
    pd.DataFrame([{k:v for k,v in data.items() if k!='offset'}|{'cell_projects':cell[0],'cell_diversity':cell[1]} for cell,data in arc.items()]).to_csv(out/'map_elites_archive.csv',index=False)
    write_json({'mode':'bounded_MAP_Elites','filled_cells':len(arc),'cells_possible':36,
        'best_fitness_on_training_scenarios':best['fitness'],'auto_applied':False,
        'independent_final_seeds_required':True,'note':'Policies mutate logits only, never historic data, legal rules, or code.'},out/'map_elites_manifest.json')
    return pd.DataFrame(history),pd.DataFrame([{k:v for k,v in a.items() if k!='offset'} for a in arc.values()])

# V4 version-stable entrypoints.
train_world_v4=train_world_v3
load_world_v4=load_world_v3
train_marl_v4=train_marl_v3
load_marl_v4=load_marl_v3
