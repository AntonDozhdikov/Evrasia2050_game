"""Scientific corpus/adapters QA for Eurasia 2050 V4.5.
Validation of prepared answers is NOT validation of generated LLM answers.
"""
from pathlib import Path
import json,hashlib,math
import pandas as pd
from eurasia_runtime import COUNTRIES,write_json

def _sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()

def check_corpora(corpora,results,run_mode='FULL'):
 corpora=Path(corpora);results=Path(results)
 rows=[]; seen={}
 for family in ['crisis','interpreter']:
  for split in ['train','holdout']:
   path=corpora/f'{family}_{split}.jsonl'
   if not path.exists():raise FileNotFoundError(path)
   valid=0;all_lines=0;identities=[];issues=[]
   for line in path.open(encoding='utf-8'):
    if not line.strip():continue
    all_lines+=1
    try:
     obj=json.loads(line); inp=obj['prompt']; ans=obj['answer']
     assert obj.get('provenance') in ('synthetic_crisis_template_not_historical_observation','simulated_numeric_state_checked')
     assert inp['synthetic'] is True and ans['synthetic'] is True
     if family=='crisis':
      assert 2026<=int(ans['year'])<=2050
      assert 1<=int(ans['duration_years'])<=12
      assert len(ans['shocks'])==4
      assert all(isinstance(v,(int,float)) and math.isfinite(v) and abs(v)<=2. for v in ans['shocks'])
      assert set(ans['affected_countries'])<=set(COUNTRIES+['GLOBAL'])
      assert ans['institutional_proposal']
      identities.append(int(obj['template_id']))
     else:
      assert abs(float(ans['mean_growth_pct'])-float(inp['mean_growth_current_pct']))<.001
      assert abs(float(ans['trade_concentration_mean'])-float(inp['trade_concentration_mean']))<.001
      actual=round(float(inp['mean_growth_current_pct'])-float(inp['mean_growth_previous_pct']),2)
      assert abs(float(ans['growth_change_pp'])-actual)<.011
      assert ans['causal_claim']=='не идентифицировано'
      assert ans['period']==inp['period']
      identities.append(str(obj['scenario_id']))
     valid+=1
    except Exception as e:
     if len(issues)<12:issues.append({'row':all_lines,'error':str(e)[:120]})
   rows.append({'family':family,'split':split,'count':all_lines,'valid':valid,
                'invalid':all_lines-valid,'examples':issues,'sha256':_sha(path)})
   seen[(family,split)]=set(identities)
 for family in ['crisis','interpreter']:
  if seen[(family,'train')]&seen[(family,'holdout')]:
   raise ValueError('Corpus split overlaps in scenario/template identities: '+family)
 df=pd.DataFrame([{k:v for k,v in r.items() if k!='examples'} for r in rows])
 df.to_csv(results/'v45_corpus_validation.csv',index=False)
 manifest={'version':'V4.5','run_mode':run_mode,'answer_origin':'synthetic_source_corpora_not_model_inference',
     'rows':rows,'identity_split_disjoint':True,'all_source_answers_valid':all(r['invalid']==0 for r in rows),
     'not_a_claim_of_trained_llm_accuracy':True}
 write_json(manifest,results/'v45_corpus_validation.json')
 if not manifest['all_source_answers_valid']:
  raise ValueError('Invalid numeric or structured synthetic examples; inspect v45_corpus_validation.json')
 return manifest

def check_lora_adapters(results,run_mode='FULL'):
 results=Path(results);out={}
 for name in ['crisis','interpreter']:
  directory=results/('lora_'+name)
  model=directory/'adapter_model.safetensors';quality=directory/'quality.json'
  if model.exists() and quality.exists():
   q=json.loads(quality.read_text());out[name]={'model_sha256':_sha(model),
     'bytes':model.stat().st_size,'training_complete':bool(q.get('training_complete')),
     'checked_holdout':int(q.get('checked_holdout',0)),
     'reported_pass_rate':q.get('pass_rate'),
     'reused_from':q.get('reused_from'),
     'has_generation_examples':(directory/'heldout_examples.json').exists(),
     'scientific_content_accepted':False,
     'caution':'Small/frozen heldout is a diagnostic; external numerical consistency has not been established.'}
  else:
   out[name]={'present':False,'reason':'SMOKE or missing adapter'}
 if run_mode=='FULL':
  if any(not v.get('training_complete') for v in out.values()):
   raise RuntimeError('At least one Qwen adapter is missing trained weights')
  if out['crisis']['model_sha256']==out['interpreter']['model_sha256']:
   raise RuntimeError('Two independent LoRA adapters have identical bytes')
 write_json({'version':'V4.5','adapters':out,'model_outputs_verified_on_large_holdout':False},results/'v45_adapter_validation.json')
 return out
