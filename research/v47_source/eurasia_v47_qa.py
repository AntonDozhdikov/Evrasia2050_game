"""EURASIA V4.7: executable economic audits, independent of training metrics."""
from pathlib import Path
import hashlib,json
import numpy as np

def _write(path,obj):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
 return obj

def economic_regression(prep,models,world,catalog,scenarios,out,strict=True):
 from eurasia_runtime import EurasiaEnv,N,ACT_NAMES
 kwargs=dict(prep=prep,models=models,world_report=world,catalog=catalog,
             scenarios=scenarios,seed=97123,horizon=5,crisis_mode='scenario',scenario_id=scenarios[0]['scenario_id'])
 neutral=np.ones((N,len(ACT_NAMES)),dtype=int)
 propose=np.full((N,len(ACT_NAMES)),2,dtype=int)
 e=EurasiaEnv(**kwargs)
 initial=e.energy.copy()
 _,_,_,first=e.step(propose)
 first_projects=int(first['new_projects']);first_cash=float(first['project_cash_out'])
 # Controlled resource replenishment is required to force the duplicate-rejection branch.
 e.energy[:]=1.0
 _,r_repeat,_,repeat=e.step(propose)
 rejected_new_projects=e.last_new_projects.copy()
 second_cash=float(repeat['project_cash_out'])
 _,_,_,mature=e.step(neutral)
 # Tests verify outcomes, not preferred strategies or project quotas.
 checks={
  'initial_project_cash_positive':first_projects>0 and first_cash>0,
  'duplicate_offers_rejected':repeat['rejected_duplicate_pairs']>0,
  'duplicate_project_count_zero':repeat['new_projects']==0,
  'duplicate_volume_zero':abs(repeat['realized_project_volume_total'])<1e-12,
  'duplicate_project_cash_zero':abs(second_cash)<1e-12,
  'no_duplicate_macro_project_term':bool(np.allclose(rejected_new_projects,0.0)),
  'lagged_maturity':first['projects_matured']==0 and repeat['projects_matured']==0 and mature['projects_matured']>0,
  'reward_no_activity_terms':set(first['reward_components_mean']).isdisjoint({'project_count','agreements_count','mobility_agreements_count'}),
  'reward_exact_component_sum':abs(sum(repeat['reward_components_mean'].values())-float(repeat['mean_reward']))<1e-5,
  'budget_finite':bool(np.isfinite(e.energy).all() and (e.energy>=0).all()),
  'no_free_idle_capital':bool(np.all(e.energy<=1.5+1e-8)),
  'eight_countries':N==8,
  'action_heads_unchanged':len(ACT_NAMES)==6,
 }
 # Expose independent counterfactual: repeat-offer with all projects blocked carries exactly zero realized volume.
 baseline=EurasiaEnv(**kwargs);baseline.step(propose)
 baseline.energy[:]=1.0
 _,_,_,ref=baseline.step(neutral)
 checks['repeat_and_neutral_same_realized_project_volume']=abs(float(ref['realized_project_volume_total'])-float(repeat['realized_project_volume_total']))<1e-12
 checks['no_phantom_cash_in_repeat']=repeat['project_cash_out']==ref['project_cash_out']==0
 result={'version':'V4.7','checks':checks,'passed':all(checks.values()),
         'initial_energy':initial.tolist(),'first_year':first,'duplicate_year':repeat,'maturity_year':mature,
         'note':'Synthetic model accounting. No empirical causal interpretation.'}
 _write(Path(out)/'v47_economic_regression.json',result)
 if strict and not result['passed']:raise AssertionError('V4.7 economic regression: '+str({k:v for k,v in checks.items() if not v}))
 return result

def structural_regression(src,meta,out,nb_source_path=None):
 import ast
 src=Path(src);meta=Path(meta)
 names=['eurasia_runtime.py','eurasia_v4.py','eurasia_lora.py','eurasia_diagnostics.py',
        'eurasia_progress.py','eurasia_world_v42.py','eurasia_marl_v42.py',
        'eurasia_world_v43.py','eurasia_marl_v43.py','eurasia_world_v44.py',
        'eurasia_marl_v44.py','eurasia_v45_panel.py','eurasia_v45_finalize.py',
        'eurasia_v45_qa.py','eurasia_v46_guardrails.py','eurasia_restore_qa.py']
 checks={'all_v46_modules':all((src/f).is_file() for f in names),
   'new_v47_audit_module':(src/'eurasia_v47_qa.py').is_file(),
   '100_crises':len(json.loads((meta/'crises_future_100.json').read_text()))==100,
   '20_scenarios':len(json.loads((meta/'scenarios_20.json').read_text()))==20,
   '13_world_families':False,
   'hetero_proxy':False,'bounded_rule_evolution':False,
   'quality_diversity':False,'qlora_two_adapters':False,
   'paired_selector':False,'guardrails':False}
 from eurasia_world_v44 import FAMILIES
 checks['13_world_families']=len(FAMILIES)>=13
 p=(src/'eurasia_v4.py').read_text()
 checks['hetero_proxy']='def train_hetero_proxy_v4' in p
 checks['bounded_rule_evolution']='def bounded_rule_evolution' in p
 checks['quality_diversity']='def quality_diversity44' in (src/'eurasia_marl_v44.py').read_text()
 checks['qlora_two_adapters']='def qlora_train' in (src/'eurasia_lora.py').read_text()
 checks['paired_selector']='def finalize_policy' in (src/'eurasia_v45_finalize.py').read_text()
 checks['guardrails']='def audit_selected' in (src/'eurasia_v46_guardrails.py').read_text()
 for f in names+['eurasia_v47_qa.py']:
  if (src/f).exists():ast.parse((src/f).read_text())
 result={'version':'V4.7','checks':checks,'passed':all(checks.values())}
 _write(Path(out)/'v47_structural_regression.json',result)
 if not result['passed']:raise AssertionError('V4.7 structural regression '+str(checks))
 return result
