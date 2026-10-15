"""V4.4 MAPPO selection + bounded DGM-inspired quality-diversity lineage.
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




# V4.4: bounded state-gated parameters. No change to the actor neural network or
# historical data. A state-dependent policy can adapt after initial investment.
class EvoActor44(nn.Module):
 def __init__(self,base,parameters=None):
  super().__init__()
  self.base=base.base if isinstance(base,EvoActor43) else base
  # Four gates: static, prior-crisis exposure, capital shortage, elapsed years.
  v=np.zeros((4,N,len(ACT_NAMES),3),np.float32) if parameters is None else np.asarray(parameters,np.float32)
  if v.shape==(N,len(ACT_NAMES),3):
   v=np.concatenate([v[None],np.zeros((3,N,len(ACT_NAMES),3),np.float32)])
  if v.shape!=(4,N,len(ACT_NAMES),3):raise ValueError('V4.4 gated policy parameters shape')
  self.register_buffer('evolution_gates',torch.tensor(np.clip(v,-1.25,1.25)))
 def forward(self,obs):
  # Environment observation contract: [-7]=capital,[-6]=year/2050,[-2]=last crisis.
  # These covariates are available when the decision is made, no future leakage.
  crisis=torch.clamp(obs[:,:,-2]*5.0,0.,1.)
  shortage=torch.clamp((.60-obs[:,:,-7])*2.,0.,1.)
  elapsed=torch.clamp((obs[:,:,-6]*2050.0-2025.0)/20.0,0.,1.)
  g=self.evolution_gates
  shifts=(g[0].unsqueeze(0)+crisis[:,:,None,None]*g[1].unsqueeze(0)+
    shortage[:,:,None,None]*g[2].unsqueeze(0)+elapsed[:,:,None,None]*g[3].unsqueeze(0))
  return self.base(obs)+shifts

def load_marl_v44(path):
 ck=torch.load(path,map_location='cpu',weights_only=True)
 if ck.get('version')!=44:raise ValueError('Expected V4.4 model')
 actor=Actor(ck['obs_dim']);crit=Critic(ck['obs_dim'])
 actor.load_state_dict(ck['actor']);crit.load_state_dict(ck['critic'])
 return EvoActor44(actor,ck['evolution_gates']).eval(),crit.eval()

def _trajectory(prep,models,world,actor,catalog,scenarios,seed,scenario_id=None,horizon=26):
 h,r=simulate(prep,models,world,actor,catalog,scenarios,seed=seed,
  policy='MAPPO',horizon=horizon,sample_actions=False,
  scenario_id=scenario_id,crisis_mode='scenario' if scenario_id else 'stochastic')
 summary=_summarize(h,r)
 summary['late_projects']=int(sum(z['new_projects'] for z in h if z['year']>=2029))
 summary['late_agreements']=int(sum(z['new_agreements'] for z in h if z['year']>=2029))
 summary['project_years']=int(len({z['year'] for z in h if z['new_projects']>0}))
 summary['crisis_steps']=int(sum(bool(z['crises']) for z in h))
 summary['mean_capital_budget']=float(np.mean([z.get('capital_budget_total',0) for z in h]))
 summary['net_project_cash']=float(summary['benefit']-summary['cash_out'])
 summary['action_fingerprint']=[int(x) for x in np.asarray([z['actions'] for z in h]).ravel()]
 return summary

def _robust_multi(summaries):
 d={k:float(np.mean([v[k] for v in summaries])) for k in summaries[0] if isinstance(summaries[0][k],(int,float,np.integer,np.floating))}
 d['min_reward']=float(min(v['reward'] for v in summaries))
 d['project_years_min']=int(min(v['project_years'] for v in summaries))
 d['late_projects_min']=int(min(v['late_projects'] for v in summaries))
 d['fingerprint_var']=float(np.mean([np.mean(np.array(summaries[0]['action_fingerprint'])!=np.array(v['action_fingerprint']))
  for v in summaries[1:]])) if len(summaries)>1 else 0.
 return d

def _paired_scenario_sensitivity(prep,models,world,actor,catalog,scenarios,seed,horizon=16):
 # Same policy-randomness and seed; crises follow different named scenarios.
 sid=[x['scenario_id'] for x in scenarios[:min(4,len(scenarios))]]
 if len(sid)<2:return 0.
 traces=[_trajectory(prep,models,world,actor,catalog,scenarios,seed,
                    scenario_id=x,horizon=horizon)['action_fingerprint'] for x in sid]
 return float(np.mean([np.mean(np.asarray(traces[0])!=np.asarray(x)) for x in traces[1:]]))

def quality_diversity44(prep,models,world,base,catalog,scenarios,out,mode='FULL',seed=42,progress_callback=None):
 """Bounded DGM-inspired multi-emitter quality diversity; no code mutation.
    Three completely disjoint seed groups. Selection never uses held-out outcomes.
    Only the selected candidate is checked on heldout exactly once.
 """
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 origin=(base.evolution_gates.detach().cpu().numpy().copy() if isinstance(base,EvoActor44) else
   np.concatenate([base.offset.detach().cpu().numpy()[None],np.zeros((3,N,len(ACT_NAMES),3),np.float32)])
       if isinstance(base,EvoActor43) else np.zeros((4,N,len(ACT_NAMES),3),np.float32))
 base=base.base if isinstance(base,(EvoActor43,EvoActor44)) else base
 rng=np.random.default_rng(seed)
 G,P=(7,11) if mode=='FULL' else (2,3)  # 77 candidate evaluations; unchanged time budget
 training=[seed+4011,seed+4147] if mode=='FULL' else [seed+4011]
 validation=[seed+5011,seed+5191] if mode=='FULL' else [seed+5011]
 heldout=[seed+7011,seed+7207] if mode=='FULL' else [seed+7011]
 reference=[_trajectory(prep,models,world,EvoActor44(base,origin),catalog,scenarios,ss,horizon=19 if mode=='FULL' else 7) for ss in validation]
 basem=_robust_multi(reference)
 archive={};candidates=[];lineage=[];events=[];memo={};operator_success={k:[1,1] for k in ['gaussian','directed','crossover','differential','restart','conditional']}
 all_descriptors=[];plateau_generations=0;best_archive_fitness=-float('inf');stop_reason='EVALUATION_BUDGET'
 def measure(v,seeds,horizon):
  a=EvoActor44(base,v)
  return _robust_multi([_trajectory(prep,models,world,a,catalog,scenarios,k,horizon=horizon) for k in seeds])
 def descriptor(m):
  # FIX of V4.3: earlier diversification .65 threshold collapsed all candidates into 1 row.
  # Two independently varying observables: project initiation (0-5) and temporal
  # spread of their starts (0-5); third crisis variance is documented separately.
  return (int(np.clip(np.floor(m['projects']/2),0,5)),int(np.clip(np.floor(m['project_years']*.85),0,5)))
 def quality(m,v):
  # Reward remains generated by the simulator. Optimization diagnostics are NOT
  # additional rewards paid to agents. Risk/feasibility constraints matter.
  if not np.isfinite(m['reward']):return -1.e6
  return float(m['reward']-.025*np.mean(np.square(v))-.03*max(0,-m['net_project_cash']))
 for gen in range(G):
  for iteration in range(P):
   ids=list(archive)
   if gen==0 and iteration==0:
    v=origin.copy();par=[];op='identity'
   elif gen==0 and iteration==1:
    v=origin.copy();v[0,:,1:3,2]+=.45;v[0,:,4,2]+=.40
    v[3,:,1:3,2]+=.35;par=[];op='conditional'
   elif gen==0 and iteration==2:
    v=origin.copy();v[1,:,3,2]+=.65;v[1,:,0,0]+=.45
    v[2,:,1,2]-=.70;par=[];op='conditional'
   else:
    # Bandit selector among mutation emitters (ME-MAP-Elites-style heuristic).
    choices=['gaussian','directed','crossover','differential','restart','conditional']
    ucb=np.array([operator_success[q][0]/operator_success[q][1]+
        .30*np.sqrt(np.log(2+len(candidates))/operator_success[q][1]) for q in choices])
    op=choices[int(rng.choice(np.flatnonzero(ucb>=ucb.max()-1e-10)))]
    if not ids or op=='restart':
     v=rng.normal(0,.35,(4,N,len(ACT_NAMES),3)).astype('float32')
     par=[]
    else:
     # archive parents include quality and novelty, instead of only latest champion
     keys=ids
     nw=np.array([.2+max(.01,archive[q]['novelty']) for q in keys],dtype=float)
     nw/=nw.sum()
     a=archive[keys[int(rng.choice(len(keys),p=nw))]]
     v=a['parameters'].copy();par=[a['id']]
     if op in ('crossover','differential') and len(keys)>1:
      b=archive[keys[int(rng.integers(len(keys)))]];par.append(b['id'])
      if op=='crossover':
       mix=rng.uniform(.15,.85);v=mix*v+(1-mix)*b['parameters']
      else:v=v+.55*(v-b['parameters'])
     sigma=.29*(.93**gen)
     v=v+rng.normal(0,sigma,v.shape).astype(np.float32)
    if op=='directed':v[3,:,1:3,2]+=.16;v[3,:,4,2]+=.12
    if op=='conditional':v[1,:,3,2]+=.30;v[1,:,0,0]+=.2;v[2,:,1,2]-=.25
   v=np.clip(v,-1.25,1.25).astype('float32')
   key=hashlib.sha256(v.tobytes()).hexdigest()[:14]
   if key in memo:continue
   memo[key]=1
   m=measure(v,training,19 if mode=='FULL' else 7)
   d=descriptor(m);fitness=quality(m,v)
   novelty=float(np.mean([np.linalg.norm(np.subtract(d,z)) for z in all_descriptors])) if all_descriptors else 3.
   all_descriptors.append(d)
   old=archive.get(d);improved=old is None or fitness>old['fitness']
   operator_success.setdefault(op,[1,1]);operator_success[op][1]+=1
   if improved:operator_success[op][0]+=1
   trial={'id':key,'generation':gen+1,'operator':op,'parent_ids':par,'parameters':v,
      'fitness':fitness,'novelty':novelty,'descriptor':d,**m}
   candidates.append(trial)
   if improved:archive[d]=trial
   lineage.append({'id':key,'parents':json.dumps(par),'generation':gen+1,'operator':op,
      'cell_project':d[0],'cell_temporal':d[1],'fitness':fitness,'novelty':novelty,
      'projects':m['projects'],'project_years':m['project_years'],
      'late_projects':m['late_projects'],'reward':m['reward'],'archive_improved':improved})
   events.append({'generation':gen+1,'candidate':iteration+1,'cell_project':d[0],
      'cell_temporal':d[1],'reward':m['reward'],'fitness':fitness,
      'late_projects':m['late_projects'],'filled_cells':len(archive)})
  # Conservative QD early stop: preserve archive, evaluate no holdout while evolving.
  current_best=max([v['fitness'] for v in archive.values()],default=-float('inf'))
  if current_best>best_archive_fitness+.002:
   best_archive_fitness=current_best;plateau_generations=0
  else:plateau_generations+=1
  if progress_callback:progress_callback((gen+1)/G,f'V4.6 QD {gen+1}/{G}; niches={len(archive)}; plateau={plateau_generations}')
  if gen>=3 and plateau_generations>=int(__import__('os').environ.get('EURASIA_V46_QD_PATIENCE','2')):
   stop_reason='QD_ARCHIVE_PLATEAU';break
 # Validate archive elites on previously unused seeds and multiple scenario types;
 # NEVER select on heldout seeds or hidden historical World Model test.
 final=sorted(archive.values(),key=lambda x:x['fitness'],reverse=True)[:min(12,len(archive))]
 compare=[];winner=None;best=(-float('inf'))
 for c in [{'id':'base','parameters':origin}]+final:
  v=c['parameters'];m=measure(v,validation,26 if mode=='FULL' else 8)
  # Separate scenario-pair check on validation seed; training contains stochastic shocks.
  crisis=_paired_scenario_sensitivity(prep,models,world,EvoActor44(base,v),catalog,scenarios,validation[0],horizon=13 if mode=='FULL' else 6)
  feasible=(m['agreements']>=1 and m['matured']>=1 and m['projects']>=1 and
     m['reward']>=basem['reward']-.12 and m['min_reward']>=basem['min_reward']-.40)
  late=(m['late_projects']>=1 or m['project_years']>=2)
  # Candidate promotion prioritizes projects beyond first year AND actual policy
  # sensitivity; if no candidate qualifies it never invents adaptation.
  adaptive=bool(feasible and late and crisis>.005)
  score=quality(m,v)+.005*min(m['late_projects'],10)+.10*min(crisis,.10)
  compare.append({'id':c['id'],'economically_feasible':feasible,'adaptive':adaptive,
        'crisis_action_difference':crisis,**{k:v for k,v in m.items() if k!='action_fingerprint'}})
  if adaptive and score>best:
   best=score;winner=v.copy()
 # If stringent gate fails, do not silently apply unvalidated evolution.
 promoted=winner is not None
 chosen=winner if promoted else origin
 # One single independent heldout assessment, after selection is frozen.
 hold=measure(chosen,heldout,26 if mode=='FULL' else 8)
 held_crisis=_paired_scenario_sensitivity(prep,models,world,EvoActor44(base,chosen),catalog,scenarios,heldout[0],horizon=15 if mode=='FULL' else 6)
 held_pass=bool(hold['matured']>=1 and hold['late_projects']>=1 and
     hold['project_years']>=2 and held_crisis>.005 and hold['reward']>=basem['reward']-.15)
 if not (promoted and held_pass):
  chosen=origin.copy();promoted=False
  # record rejection without retesting/choosing a new policy on heldout
 np.savez_compressed(out/'quality_diversity_offsets.npz',**{c['id']:c['parameters'] for c in archive.values()})
 pd.DataFrame(lineage).to_csv(out/'evolution_lineage.csv',index=False)
 pd.DataFrame(events).to_csv(out/'map_elites_trials.csv',index=False)
 pd.DataFrame(compare).to_csv(out/'evolution_validation.csv',index=False)
 pd.DataFrame([{'id':c['id'],'fitness':c['fitness'],'projects':c['projects'],
     'late_projects':c['late_projects'],'project_years':c['project_years'],
     'cell_project':d[0],'cell_temporal':d[1],'novelty':c['novelty'],
     'operator':c['operator']} for d,c in archive.items()]).to_csv(out/'map_elites_archive.csv',index=False)
 manifest={'version':'V4.4','algorithm':'state_gated_ME_MAP_Elites_DGM_inspired',
    'evaluations_requested':G*P,'evaluations_actual':len(events),'early_stop_reason':stop_reason,'cells_possible':36,
    'filled_cells':len(archive),'archive_diversification_axis':'project_years_not_trade_threshold',
    'state_gates':['static','last_crisis','capital_shortage','elapsed_years'],
    'validated_adaptive_candidates':int(sum(r['adaptive'] for r in compare)),
    'selected_promoted':bool(promoted),'independent_heldout_integrative':bool(held_pass),
    'heldout':{k:v for k,v in hold.items() if k!='action_fingerprint'},
    'heldout_crisis_action_difference':held_crisis,
    'operator_success':operator_success,'validation_seeds':validation,
    'training_seeds':training,'heldout_seeds':heldout,
    'scientific_caution':'Synthetic MARL economics, no causal real-world integration claims',
    'not_full_DGM':True,'no_self_generated_code_execution':True,'rollback_if_not_approved':True}
 write_json(manifest,out/'map_elites_manifest.json')
 return EvoActor44(base,chosen).eval(),pd.DataFrame(events),manifest

def save_marl44_evolved(path,actor,manifest):
 ck=torch.load(path,map_location='cpu',weights_only=True)
 if not isinstance(actor,EvoActor44):raise TypeError('EvoActor44 required')
 ck['evolution_gates']=actor.evolution_gates.cpu()
 ck['evolution_promoted']=bool(manifest['selected_promoted'])
 ck['evolution_heldout_adaptive']=bool(manifest['independent_heldout_integrative'])
 ck['version']=44;ck['algo']='MAPPO_CTDE_V44_STATE_GATED_QD'
 torch.save(ck,path)

def _crisis_counterfactual_refinement(base,prep,models,world,catalog,scenarios,seed,steps=35):
 """Bounded teacher regularisation on SYNTHETIC stress contrasts only.
    Risk instruction is a designed policy constraint, NOT an observed action.
    Candidate is not promoted without a separate economic validation.
 """
 import torch.nn.functional as F
 a=copy.deepcopy(base).cpu().train();teacher=copy.deepcopy(base).cpu().eval()
 torch.manual_seed(seed);optim=torch.optim.AdamW(a.parameters(),lr=1.2e-4)
 environments=[EurasiaEnv(prep,models,world,catalog,scenarios,seed+1800+i,horizon=20) for i in range(3)]
 rows=[]
 for k in range(steps):
  real=[];truth=[];stressed=[];synth=[]
  for env in environments:
   if env.steps>=env.horizon:env.reset()
   ob=env.observe().copy();act=_expert_actions(env)
   forced=ob.copy();forced[:,-2]=.40
   # Risk exposure + constrained investment capital are intervention inputs;
   # they are not statistical observations from 2000–25.
   forced[:,-7]=np.minimum(forced[:,-7],.40)
   a_stress=act.copy();a_stress[:,3]=2;a_stress[:,0]=0;a_stress[:,1]=0
   real.append(ob);truth.append(act);stressed.append(forced);synth.append(a_stress)
   env.step(act)
  xb=torch.tensor(np.asarray(real),dtype=torch.float32)
  yb=torch.tensor(np.asarray(truth),dtype=torch.long)
  xcf=torch.tensor(np.asarray(stressed),dtype=torch.float32)
  ycf=torch.tensor(np.asarray(synth),dtype=torch.long)
  lreal=a(xb);lcf=a(xcf)
  with torch.no_grad():ref=teacher(xb)
  ce0=F.cross_entropy(lreal.reshape(-1,3),yb.flatten())
  ce1=F.cross_entropy(lcf.reshape(-1,3),ycf.flatten())
  anchor=F.kl_div(F.log_softmax(lreal,-1),F.softmax(ref,-1),reduction='batchmean')
  loss=.55*ce0+.45*ce1+.18*anchor
  optim.zero_grad();loss.backward();nn.utils.clip_grad_norm_(a.parameters(),.65);optim.step()
  rows.append({'step':k+1,'legal_teacher_ce':float(ce0.detach()),
    'synthetic_counterfactual_ce':float(ce1.detach()),'teacher_KL':float(anchor.detach())})
 return a.cpu().eval(),pd.DataFrame(rows)

def train_marl_v44(*args,**kwargs):
 # Retrain new PPO variants, but KEEP THE PREVIOUS SUCCESSFUL V4.3 policy as
 # a competing immutable candidate. No use of scientific heldout seeds for choice.
 a,c,h,validation=train_marl_v43(*args,**kwargs)
 prep,models,world,catalog,scenarios,out=args[:6]
 out=Path(out);seed=int(kwargs.get('seed',42));mode=kwargs.get('mode','FULL')
 candidate=EvoActor44(a.base,a.offset.detach().cpu().numpy())
 oldpath=out/'v43_safe'/'mappo.pt'
 rows=[]
 val_seeds=[seed+6201,seed+6323] if mode=='FULL' else [seed+6201]
 def evaluate(label,actor):
  stats=_robust_multi([_trajectory(prep,models,world,actor,catalog,scenarios,ss,
         horizon=20 if mode=='FULL' else 7) for ss in val_seeds])
  row={'candidate':label,'val_reward':stats['reward'],'val_projects':stats['projects'],
       'val_matured':stats['matured'],'val_agreements':stats['agreements'],
       'late_projects':stats['late_projects'],'val_project_years':stats['project_years']}
  rows.append(row)
  return row
 current=evaluate('V4.4_fresh_MAPPO',candidate)
 # Stress-aware distillation is *just another candidate*: no automatic approval.
 if mode=='FULL':
  try:
   refined,log=_crisis_counterfactual_refinement(a.base,prep,models,world,catalog,scenarios,
             seed=seed+4600,steps=38)
   log.to_csv(out/'crisis_conditional_refinement.csv',index=False)
   trained=EvoActor44(refined,a.offset.detach().cpu().numpy())
   rv=evaluate('V4.4_stress_refined',trained)
   if (rv['val_projects']>=1 and rv['val_matured']>=1 and
       rv['val_reward']>=current['val_reward']-.08 and
       (rv['val_reward']>current['val_reward'] or rv['late_projects']>current['late_projects'])):
    candidate=trained;current=rv
    ck=torch.load(out/'mappo.pt',map_location='cpu',weights_only=True)
    ck['actor']=refined.state_dict();ck['selected_variant']='V4.4_STRESS_REFINED'
    torch.save(ck,out/'mappo.pt')
  except Exception as err:
   rows.append({'candidate':'V4.4_stress_refinement_error','error':str(err)[:200]})
 if oldpath.exists():
  try:
   oldck=torch.load(oldpath,map_location='cpu',weights_only=True)
   oldactor=Actor(oldck['obs_dim']);oldactor.load_state_dict(oldck['actor'])
   oldpar=np.zeros((4,N,len(ACT_NAMES),3),np.float32)
   oldpar[0]=np.asarray(oldck['evolution_offset'],np.float32)
   previous=EvoActor44(oldactor,oldpar).eval()
   old=evaluate('V4.3_frozen_evolved',previous)
   # Prior is eligible if its actual joint-project economics are at least as
   # good as the newly fitted MAPPO; no artificial agreement bonus to PPO reward.
   better=bool(old['val_projects']>=1 and old['val_matured']>=1 and
     old['val_reward']>=current['val_reward']-.10 and
     (current['val_projects']<1 or old['val_reward']>=current['val_reward']))
   if better:
    candidate=previous;c=Critic(oldck['obs_dim']);c.load_state_dict(oldck['critic'])
    ck=torch.load(out/'mappo.pt',map_location='cpu',weights_only=True)
    ck['actor']=oldck['actor'];ck['critic']=oldck['critic'];ck['obs_dim']=oldck['obs_dim']
    ck['selected_variant']='V4.3_FROZEN_EVOLVED_SAFE';ck['evolution_offset']=torch.as_tensor(oldpar[0])
    torch.save(ck,out/'mappo.pt')
  except Exception as err:
   rows.append({'candidate':'V4.3_reference_load_error','error':str(err)[:200]})
 pd.DataFrame(rows).to_csv(out/'v43_frozen_vs_v44_new_validation.csv',index=False)
 # No holdout tested in training candidate selection. Next QD uses disjoint seeds.
 return candidate,c,h,validation
