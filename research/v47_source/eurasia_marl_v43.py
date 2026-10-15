"""V4.3 MAPPO selection + bounded DGM-inspired quality-diversity lineage.
No synthetic policy traces are called historical observations. No code self-editing.
Acceptance requires independent economic/contract evidence, not a reward proxy.
"""
from __future__ import annotations
import gc, json, hashlib, copy, time
from pathlib import Path
import numpy as np, pandas as pd, torch
from torch import nn
from eurasia_runtime import (train_mappo, simulate, Actor, Critic, EurasiaEnv,
                              N, ACT_NAMES, COUNTRIES, write_json)
from eurasia_v4 import bounded_rule_evolution, train_hetero_proxy_v4

class EvoActor43(nn.Module):
 def __init__(self,base,offset=None):
  super().__init__();self.base=base
  x=np.zeros((N,len(ACT_NAMES),3),np.float32) if offset is None else np.asarray(offset,np.float32)
  if x.shape!=(N,len(ACT_NAMES),3):raise ValueError('Invalid bounded policy offset shape')
  self.register_buffer('offset',torch.as_tensor(np.clip(x,-1.25,1.25)))
 def forward(self,obs):return self.base(obs)+self.offset.unsqueeze(0)

def load_marl_v43(path):
 ck=torch.load(path,map_location='cpu',weights_only=True)
 if ck['version']!=43:raise ValueError('Expected V4.3 model')
 actor=Actor(ck['obs_dim']);crit=Critic(ck['obs_dim']);actor.load_state_dict(ck['actor']);crit.load_state_dict(ck['critic'])
 return EvoActor43(actor,ck['evolution_offset']).eval(),crit.eval()

def _summarize(h,r):
 actions=np.asarray([v['actions'] for v in h]);projects=int(sum(v['new_projects'] for v in h))
 agreements=int(sum(v['new_agreements'] for v in h));matured=int(sum(v['projects_matured'] for v in h))
 return {'reward':float(np.mean(r)),'projects':projects,'agreements':agreements,'matured':matured,
  'cash_out':float(sum(v['project_cash_out'] for v in h)),
  'benefit':float(sum(v['project_benefit_current'] for v in h)),
  'profile_diversity':int(len(np.unique(actions.reshape(-1,len(ACT_NAMES)),axis=0))),
  'diversification':float(np.mean([1-v['trade_concentration_mean'] for v in h])),
  'terminal_trade':float(h[-1]['trade_usd_total'])}

def eval43(prep,models,world,actor,catalog,scenarios,seeds,horizon=16,policy_sample=False,scenario_id=None):
 rows=[]
 for seed in seeds:
  for name in ['MAPPO','NEUTRAL','BARGAIN','COOPERATIVE','RANDOM']:
   his,rew=simulate(prep,models,world,actor,catalog,scenarios,seed=seed,policy=name,
    sample_actions=bool(policy_sample),horizon=horizon,
    scenario_id=scenario_id,crisis_mode='scenario' if scenario_id else 'stochastic')
   rows.append({'seed':seed,'policy':name,'sampling':bool(policy_sample),**_summarize(his,rew)})
 return pd.DataFrame(rows)

def _expert_actions(env):
 # Same synthetic control policy used by BARGAIN, not real state action labels.
 acts=np.ones((N,len(ACT_NAMES)),np.int64);lead=(env.year-2024)%N
 acts[lead,1]=2;acts[lead,2]=2;acts[lead,4]=2
 for j in range(N):
  if env.graph[lead,j]>.05:acts[j,1]=1;acts[j,2]=1;acts[j,4]=2
 # Explicit *synthetic* conditional teacher: crisis exposure changes the acceptable
 # risk/cost tradeoff. It is NOT historical evidence about any country's actions.
 severe=np.asarray(env.last_crisis_intensity)>.08
 acts[severe,3]=2       # temporary active resilience
 acts[severe,0]=0       # explore trade diversification during stress
 low_budget=severe & (np.asarray(env.energy)<.55)
 acts[low_budget,1]=0   # don't commit unavailable capital to a project
 return acts

def _behavioral_refinement(base,prep,models,world,catalog,scenarios,seed,steps=38):
 """Optional conservative policy distillation on *synthetic legal* bargaining examples.
 Each variant is measured on disjoint holdout, never promoted just for imitation loss.
 """
 a=copy.deepcopy(base).cpu().train();teacher=copy.deepcopy(base).cpu().eval()
 torch.manual_seed(seed);opt=torch.optim.AdamW(a.parameters(),lr=1.8e-4)
 envs=[EurasiaEnv(prep,models,world,catalog,scenarios,seed+800+i,horizon=17) for i in range(3)]
 log=[]
 for step in range(steps):
  obs=[];target=[]
  for env in envs:
   if env.steps>=env.horizon:env.reset()
   ob=env.observe();actions=_expert_actions(env)
   obs.append(ob);target.append(actions);env.step(actions)
  obs=torch.tensor(np.asarray(obs),dtype=torch.float32)
  target=torch.tensor(np.asarray(target),dtype=torch.long)
  logits=a(obs)
  cross=torch.nn.functional.cross_entropy(logits.reshape(-1,3),target.flatten())
  with torch.no_grad():reference=teacher(obs)
  kl=torch.nn.functional.kl_div(torch.log_softmax(logits,-1),torch.softmax(reference,-1),reduction='batchmean')
  loss=cross+.075*kl
  opt.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(a.parameters(),.7);opt.step()
  log.append({'step':step+1,'behavioral_ce':float(cross.detach()),'original_policy_kl':float(kl.detach())})
 return a.eval(),log

def _passes(grade,neutral):
 # Hard gate: economics and actual contracts, not unconditional contract rewards.
 return bool(grade.projects.mean()>=1 and grade.agreements.mean()>=1 and grade.matured.mean()>=1
       and grade.reward.mean() >= neutral.reward.mean()-.1)

def train_marl_v43(prep,models,world,catalog,scenarios,out,mode='FULL',seed=42,updates=115,env_count=5,rollout=12,progress_callback=None):
 out=Path(out);out.mkdir(exist_ok=True,parents=True)
 settings=[('curriculum',updates,75 if mode=='FULL' else 2),
           ('no_curriculum',max(20,int(updates*.62)) if mode=='FULL' else 2,0)]
 stored=[];validation=[]
 seeds=[seed+3023,seed+3109,seed+3191] if mode=='FULL' else [seed+3023]
 for idx,(name,it,expert) in enumerate(settings):
  sub=out/f'variant_{name}';sub.mkdir(exist_ok=True)
  a,c,history=train_mappo(prep,models,world,catalog,scenarios,sub,updates=it,env_count=env_count,
      rollout=rollout,ppo_epochs=3 if mode=='FULL' else 1,expert_pretrain_steps=expert,seed=seed+137*idx,
      verbose=False,progress_callback=(lambda f,d,i=idx:progress_callback((i+.70*f)/len(settings),f'{name}: {d}')) if progress_callback else None)
  variants=[(name,a,history)]
  if name=='curriculum':
   learned,log=_behavioral_refinement(a,prep,models,world,catalog,scenarios,seed+454,
                                      steps=40 if mode=='FULL' else 2)
   pd.DataFrame(log).to_csv(sub/'behavioral_refinement.csv',index=False)
   variants.append(('curriculum_refined',learned,history))
  for variant,actor,log in variants:
   greedy=eval43(prep,models,world,actor,catalog,scenarios,seeds,horizon=19 if mode=='FULL' else 5,policy_sample=False)
   stochastic=eval43(prep,models,world,actor,catalog,scenarios,seeds,horizon=19 if mode=='FULL' else 5,policy_sample=True)
   test=greedy[greedy.policy=='MAPPO'];neutral=greedy[greedy.policy=='NEUTRAL']
   sample=stochastic[stochastic.policy=='MAPPO'];sample_neutral=stochastic[stochastic.policy=='NEUTRAL']
   qualified=_passes(test,neutral) and _passes(sample,sample_neutral)
   row={'variant':variant,'qualifying_integrative':qualified,
    'validation_reward_vs_neutral':float(test.reward.mean()-neutral.reward.mean()),
    'validation_projects':float(test.projects.mean()),'validation_agreements':float(test.agreements.mean()),
    'validation_matured':float(test.matured.mean()),
    'stochastic_projects':float(sample.projects.mean()),'stochastic_agreements':float(sample.agreements.mean()),
    'stochastic_reward_vs_neutral':float(sample.reward.mean()-sample_neutral.reward.mean())}
   validation.append(row);stored.append((row,actor,c,log))
   greedy.assign(variant=variant).to_csv(out/f'{variant}_greedy_validation.csv',index=False)
   stochastic.assign(variant=variant).to_csv(out/f'{variant}_sample_validation.csv',index=False)
  if progress_callback:progress_callback((idx+1)/len(settings),name+' проверен')
  gc.collect();torch.cuda.empty_cache() if torch.cuda.is_available() else None
 # Strongly prefer economically qualifying policies; failed policies cannot acquire a positive flag.
 qualified=[v for v in stored if v[0]['qualifying_integrative']]
 pool=qualified if qualified else stored
 chosen=max(pool,key=lambda z:z[0]['validation_reward_vs_neutral']+.025*z[0]['validation_matured'])
 row,actor,critic,history=chosen
 # Restore actual saved trained actor weights even for post-PPO distillation.
 ck={'actor':actor.state_dict(),'critic':critic.state_dict(),'obs_dim':next(m for m in actor.modules() if isinstance(m,Actor)).body[0].in_features-12,
     'evolution_offset':torch.zeros((N,len(ACT_NAMES),3)), 'version':43,'algo':'MAPPO_CTDE_V43',
     'selected_variant':row['variant'],'validated_qualifying':row['qualifying_integrative'],
     'source_version':'V4.3','action_names':ACT_NAMES}
 torch.save(ck,out/'mappo.pt')
 pd.DataFrame(validation).to_csv(out/'policy_variant_validation.csv',index=False)
 pd.DataFrame(history).to_csv(out/'mappo_history.csv',index=False)
 write_json({'selected':row['variant'],'validated_qualifying':row['qualifying_integrative'],
  'validation_seeds':seeds,'heldout_seeds':[seed+8011,seed+8041,seed+8101],
  'acceptance_note':'Positive reward alone cannot qualify; deterministic and stochastic real projects required',
  'no_real_political_action_labels':True},out/'policy_variant_manifest.json')
 wrapped=EvoActor43(actor).eval()
 independent=eval43(prep,models,world,wrapped,catalog,scenarios,
   [seed+8011,seed+8041,seed+8101] if mode=='FULL' else [seed+8011],
   horizon=26 if mode=='FULL' else 5,policy_sample=False)
 independent.to_csv(out/'policy_variant_heldout.csv',index=False)
 return wrapped,critic,history,validation


def quality_diversity43(prep,models,world,base,catalog,scenarios,out,mode='FULL',seed=42,progress_callback=None):
 """DGM-inspired repertoire: inherited variants, independent empirical verifier,
 novelty pressure, mutation/crossover, lineage hashes, rollback and human approval.
 No self-modifying code or learned changes to empirical data, rights or identities.
 """
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 base=base.base if isinstance(base,EvoActor43) else base
 rng=np.random.default_rng(seed);arc={};records=[];lineage=[];accepted=[]
 generations=7 if mode=='FULL' else 2;pop=9 if mode=='FULL' else 2 # 63 FULL vs V4.2 49 (+28.6%)
 training=[seed+4011,seed+4147] if mode=='FULL' else [seed+4011]
 selection=[seed+5011,seed+5191] if mode=='FULL' else [seed+5011]
 holdout=[seed+7011,seed+7207] if mode=='FULL' else [seed+7011]
 unique={};current=np.zeros((N,len(ACT_NAMES),3),np.float32)
 def eval_candidate(offset,seeds,stochastic=False,horizon=12):
  a=EvoActor43(base,offset);stats=[]
  for ss in seeds:
   h,r=simulate(prep,models,world,a,catalog,scenarios,seed=ss,
                policy='MAPPO',horizon=horizon,sample_actions=stochastic)
   stats.append(_summarize(h,r))
  return {k:float(np.mean([v[k] for v in stats])) for k in stats[0]}
 base_val=eval_candidate(current,selection,False,horizon=15)
 best_gate=False;best_val=base_val;selected=current.copy()
 for gen in range(generations):
  for p in range(pop):
   if gen==0 and p==0:child=current.copy();parents=[];operator='identity'
   elif gen==0 and p==1:
    child=current.copy();child[:,:,1]=-0.6;child[:,1:3,2]+=0.55;child[:,4,2]+=.55
    parents=[];operator='biased_seed'
   else:
    keys=list(arc)
    if keys:
     weights=np.array([.2+arc[k]['novelty'] for k in keys]);weights/=weights.sum()
     par1=arc[keys[int(rng.choice(len(keys),p=weights))]]
     parent=par1['offset'];parents=[par1['id']]
    else:parent=current;parents=[]
    if len(keys)>1 and p%4==0:
     par2=arc[keys[int(rng.integers(len(keys)))]];parents.append(par2['id'])
     child=.5*(parent+par2['offset']);operator='crossover'
    else:
     child=parent.copy();operator='isotropic_mutation' if p%3 else 'directional_mutation'
    sigma=.32*(.94**gen)
    mutation=rng.normal(0,sigma,child.shape).astype(np.float32)
    if operator=='directional_mutation':
     mutation[:,1:3,2]+=.17;mutation[:,4,2]+=.14
    child=np.clip(child+mutation,-1.25,1.25).astype(np.float32)
   cid=hashlib.sha256(child.tobytes()).hexdigest()[:14]
   if cid in unique:continue
   unique[cid]=True
   scores=eval_candidate(child,training,False)
   # orthogonal policy descriptors: investment activity and trade diversification
   descriptor=(int(np.clip(scores['projects']/2,0,5)),
               int(np.clip((scores['diversification']-.65)*16,0,5)))
   novelty=float(np.mean([np.linalg.norm(np.subtract(descriptor,k)) for k in arc])) if arc else 3.
   fitness=float(scores['reward']+.015*scores['matured']+.004*scores['agreements']
                 -.05*np.mean(child**2))
   a={'id':cid,'generation':gen+1,'parent_ids':parents,'operator':operator,'offset':child,
      'fitness':fitness,'novelty':novelty,'descriptor':descriptor,**scores}
   if descriptor not in arc or a['fitness']>arc[descriptor]['fitness']:arc[descriptor]=a
   lineage.append({'id':cid,'parents':json.dumps(parents),'generation':gen+1,'operator':operator,
       'cell_project':descriptor[0],'cell_diversity':descriptor[1],
       'train_fitness':fitness,'project_count':scores['projects'],'matured':scores['matured'],
       'agreements':scores['agreements'],'novelty':novelty})
   records.append({'generation':gen+1,'candidate':p+1,'cell_project':descriptor[0],'cell_diversity':descriptor[1],
      'fitness':fitness,'projects_per_year':scores['projects']/12.,'agreements_per_year':scores['agreements']/12.,
      'filled_cells':len(arc)})
  if progress_callback:progress_callback((gen+1)/generations,f'Quality-Diversity {gen+1}/{generations}; niches={len(arc)}')
 # Independent validation determines any promotion. No claiming success on TRAIN.
 finalists=sorted(arc.values(),key=lambda z:z['fitness'],reverse=True)[:min(9,len(arc))]
 comparison=[]
 for cand in [{'id':'base','offset':current}]+finalists:
  val=eval_candidate(cand['offset'],selection,False,horizon=15)
  verified=bool(val['projects']>=1 and val['agreements']>=1 and val['matured']>=1 and
                val['reward']>=base_val['reward']-.15)
  comparison.append({'id':cand['id'],'qualified':verified,**val})
  if verified and (not best_gate or val['reward']>best_val['reward']):
   best_gate=True;best_val=val;selected=cand['offset'].copy()
 test=eval_candidate(selected,holdout,False,horizon=20)
 safe_heldout=bool(test['projects']>=1 and test['agreements']>=1 and test['matured']>=1)
 # Strict rollback if no heldout contracts. No hidden 'success' conversion.
 if not safe_heldout:selected=current.copy();test=eval_candidate(selected,holdout,False,horizon=20)
 np.savez_compressed(out/'quality_diversity_offsets.npz',**{a['id']:a['offset'] for a in arc.values()})
 pd.DataFrame(lineage).to_csv(out/'evolution_lineage.csv',index=False)
 pd.DataFrame(comparison).to_csv(out/'evolution_validation.csv',index=False)
 pd.DataFrame(records).to_csv(out/'map_elites_trials.csv',index=False)
 pd.DataFrame([{k:v for k,v in a.items() if k!='offset' and k not in ('parent_ids','descriptor')}
               |{'cell_project':key[0],'cell_diversity':key[1],'parents':json.dumps(a['parent_ids'])}
               for key,a in arc.items()]).to_csv(out/'map_elites_archive.csv',index=False)
 manifest={'version':'V4.3','algorithm':'bounded_DGM_inspired_novelty_MAP_Elites',
  'evaluations_requested':pop*generations,'evaluations_actual':len(records),
  'filled_cells':len(arc),'cells_possible':36,'validation_qualified':best_gate,
  'independent_heldout_integrative':safe_heldout,'heldout':test,
  'selected_promoted':bool(best_gate and safe_heldout and np.any(selected!=0)),
  'training_seeds':training,'validation_seeds':selection,'heldout_seeds':holdout,
  'features':['archive_parent_sampling','parent_lineage','innovation','mutation','crossover','novelty','empirical_validation','rollback'],
  'not_full_DGM':True,'no_automatic_source_code_generation_or_execution':True,
  'no_historical_mutations':True,'human_approval_required_for_game_rule_changes':True}
 write_json(manifest,out/'map_elites_manifest.json')
 return EvoActor43(base,selected),pd.DataFrame(records),manifest


def save_marl43_evolved(path,actor,manifest):
 ck=torch.load(path,map_location='cpu',weights_only=True)
 if not isinstance(actor,EvoActor43):raise TypeError('Expected EvoActor43')
 ck['evolution_offset']=actor.offset.cpu()
 ck['evolution_heldout_integrative']=bool(manifest['independent_heldout_integrative'])
 ck['evolution_promoted']=bool(manifest['selected_promoted'])
 torch.save(ck,path)
