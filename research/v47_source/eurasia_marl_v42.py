"""V4.2 MARL policy variants: informed negotiation curriculum vs no curriculum.
Select only on simulated validation seeds, test on separate seeds. No historical policy labels.
"""
from pathlib import Path
import json, gc
import numpy as np
import pandas as pd
import torch
from eurasia_runtime import train_mappo, simulate, Actor, Critic, N, ACT_NAMES, write_json
from eurasia_v4 import EvoActor, bounded_rule_evolution, map_elites_v4

def load_marl_v42(path):
 ck=torch.load(path,map_location='cpu',weights_only=True)
 if ck.get('version')!=42:raise ValueError('Requires V4.2 policy checkpoint')
 base=Actor(ck['obs_dim']);crit=Critic(ck['obs_dim'])
 base.load_state_dict(ck['actor']);crit.load_state_dict(ck['critic'])
 return EvoActor(base,ck['evolution_offset']).eval(),crit.eval()

def _eval_one(prep,models,world,actor,catalog,scenarios,seeds,horizon=16):
 rows=[]
 for seed in seeds:
  for pol in ['MAPPO','NEUTRAL','BARGAIN','COOPERATIVE']:
   h,reward=simulate(prep,models,world,actor,catalog,scenarios,seed=seed,policy=pol,horizon=horizon,
        sample_actions=False,crisis_mode='stochastic')
   actions=np.asarray([x['actions'] for x in h])
   rows.append({'seed':seed,'policy':pol,'reward':float(np.mean(reward)),
      'new_projects':int(sum(x['new_projects'] for x in h)),
      'new_agreements':int(sum(x['new_agreements'] for x in h)),
      'matured_projects':int(sum(x['projects_matured'] for x in h)),
      'distinct_deterministic_profiles':int(np.unique(actions.reshape(-1,len(ACT_NAMES)),axis=0).shape[0]),
      'final_total_trade_usd':h[-1]['trade_usd_total']})
 return pd.DataFrame(rows)

def train_marl_v42(prep,models,world,catalog,scenarios,out,mode='FULL',seed=42,updates=90,env_count=6,rollout=12,progress_callback=None):
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 candidates=[('curriculum',int(updates),55 if mode=='FULL' else 3),('no_curriculum',max(18,int(updates*.60)) if mode=='FULL' else 2,0)]
 if mode=='SMOKE':candidates=[('curriculum',2,2),('no_curriculum',2,0)]
 temp=[];eval_rows=[]
 for idx,(name,iterations,expert) in enumerate(candidates):
  sub=out/f'variant_{name}';sub.mkdir(exist_ok=True)
  a,c,logs=train_mappo(prep,models,world,catalog,scenarios,sub,
    updates=iterations,env_count=env_count,rollout=rollout,ppo_epochs=3 if mode=='FULL' else 1,
    expert_pretrain_steps=expert,seed=seed+111*idx,verbose=False,
    progress_callback=(lambda f,d,i=idx,n=name:progress_callback((i+f)/len(candidates),f'{n}: {d}')) if progress_callback else None)
  val=_eval_one(prep,models,world,a,catalog,scenarios,[seed+3011,seed+3029] if mode=='FULL' else [seed+3011],horizon=16 if mode=='FULL' else 5)
  vals=val[val.policy=='MAPPO']
  neutral=val[val.policy=='NEUTRAL'];score=float(vals.reward.mean()-neutral.reward.mean())
  prs=float(vals.new_projects.mean());ags=float(vals.new_agreements.mean())
  # Reject artificial highest rewards if no contracts: constrained selection, no forced success.
  qualifying=prs>=1 and ags>=1
  temp.append((name,a,c,logs,score,prs,ags,qualifying))
  eval_rows.append({'variant':name,'validation_reward_vs_neutral':score,
      'validation_projects':prs,'validation_agreements':ags,'qualifying_integrative':qualifying})
  val.assign(variant=name).to_csv(sub/'validation.csv',index=False)
  gc.collect()
  if torch.cuda.is_available():torch.cuda.empty_cache()
 qualifies=[p for p in temp if p[-1]]
 win=max(qualifies if qualifies else temp,key=lambda x:x[4]+.035*x[5]+.025*x[6])
 name,a,c,logs,score,prs,ags,qual=win
 ck=torch.load(out/f'variant_{name}'/'mappo.pt',map_location='cpu',weights_only=True)
 ck['version']=42;ck['algo']='MAPPO_V42_BILATERAL_CONTRACTS';ck['evolution_offset']=torch.zeros(N,len(ACT_NAMES),3)
 ck['curriculum_used']=name=='curriculum';ck['source_version']='V4.2'
 torch.save(ck,out/'mappo.pt')
 pd.DataFrame(eval_rows).to_csv(out/'policy_variant_validation.csv',index=False)
 pd.DataFrame(logs).to_csv(out/'mappo_history.csv',index=False)
 write_json({'selected':name,'validated_qualifying':qual,'candidate_count':len(temp),
       'selection_seeds':[seed+3011,seed+3029] if mode=='FULL' else [seed+3011],
       'independent_final_seed_min':seed+8000,
       'no_real_political_actions_as_labels':True},out/'policy_variant_manifest.json')
 a=EvoActor(a).eval();c=c.eval()
 test=_eval_one(prep,models,world,a,catalog,scenarios,[seed+8011,seed+8041] if mode=='FULL' else [seed+8011],horizon=26 if mode=='FULL' else 5)
 test.to_csv(out/'policy_variant_heldout.csv',index=False)
 return a,c,logs,eval_rows
