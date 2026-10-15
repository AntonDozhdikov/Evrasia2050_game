"""EURASIA V4: two independently fitted adapters, grounded synthetic samples, no made-up historical statistics."""
import os,re,json,gc,time,random,math
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from eurasia_runtime import COUNTRIES,simulate,write_json,seed_all,CRISIS_CHANNELS
serialize=write_json

PROPOSALS=['сохранение действующих правил','добровольное двустороннее соглашение',
           'совместный инфраструктурный фонд с согласованием участников',
           'процедура многосторонних переговоров']

def mk_crisis(k,seed,template):
    rng=np.random.default_rng(seed);ev=dict(template);year=int(rng.integers(2026,2051))
    intensity=float(np.clip(float(ev['intensity'])*rng.uniform(.8,1.2),.1,1.))
    affected=[c for c in ev.get('affected',[]) if c in COUNTRIES]
    if not affected or not any(x in COUNTRIES for x in affected):
        # Cross-border global shock, affected via graph rather than inventing an official country fact
        affected=['GLOBAL']
    duration=int(ev.get('duration',1));kind=ev['type']
    shocks=(np.array(CRISIS_CHANNELS.get(kind,CRISIS_CHANNELS['economic']))*intensity*.65).round(3).tolist()
    proposal=PROPOSALS[int(rng.integers(len(PROPOSALS)))]
    prompt={'year':year,'template_id':int(ev['id']),'event_name':ev['name'],'event_type':kind,
        'intensity':round(intensity,3),'duration_years':duration,'affected_countries':affected,
        'shock_channels':['growth','inflation','external_trade','labor'],'allowed_max_abs':2.,
        'rules':'согласие участников при институциональном изменении','synthetic':True}
    answer={'year':year,'event_type':kind,'event_template_id':int(ev['id']),'duration_years':duration,
        'affected_countries':affected,'shocks':shocks,'institutional_proposal':proposal,
        'synthetic':True,'requires_agent_approval':proposal!='сохранение действующих правил'}
    return {'id':k,'seed':seed,'template_id':int(ev['id']),'prompt':prompt,'answer':answer,
            'provenance':'synthetic_crisis_template_not_historical_observation'}

def mk_interpret(k,seed,prep,models,world_report,actor,catalog,scenarios,scenario,history=None,pos=None):
    if history is None:
        his,_=simulate(prep,models,world_report,actor,catalog,scenarios,seed=seed,
                       horizon=26,scenario_id=scenario['scenario_id'],crisis_mode='scenario')
    else:
        his=history
    rng=np.random.default_rng(seed+23)
    pos=int(rng.integers(1,len(his))) if pos is None else int(pos)
    if not 1<=pos<len(his):raise ValueError('interpret window outside historical simulation')
    prev,curr=his[pos-1],his[pos]
    diff=round(curr['mean_growth_pct']-prev['mean_growth_pct'],2)
    growth=round(curr['mean_growth_pct'],2);concent=round(curr['trade_concentration_mean'],4)
    prompt={'scenario_id':scenario['scenario_id'],'period':[prev['year'],curr['year']],
        'mean_growth_previous_pct':round(prev['mean_growth_pct'],2),
        'mean_growth_current_pct':growth,'trade_concentration_mean':concent,
        'active_crisis_count':len(curr['crises']),'projects':curr['projects'],
        'model_type':'synthetic_WorldModel_MAPPO','synthetic':True,'no_causal_identification':True}
    direction='вырос' if diff>.03 else 'снизился' if diff<-.03 else 'изменился незначительно'
    answer={'period':prompt['period'],'growth_change_pp':diff,'mean_growth_pct':growth,
        'trade_concentration_mean':concent,'interpretation':f'Средний модельный рост {direction}. Изменение: {diff:+.2f} п. п. Сценарий условный; прямое причинное влияние политики не установлено.',
        'synthetic':True,'causal_claim':'не идентифицировано'}
    return {'id':k,'seed':seed,'scenario_id':scenario['scenario_id'],'prompt':prompt,'answer':answer,
            'provenance':'simulated_numeric_state_checked'}

def create_corpora(prep,models,world_report,actor,catalog,scenarios,output,n_crisis=480,n_interpret=500,seed=42,progress_callback=None,trajectory_variants=2):
    """Generate examples with a small cache of 26-year trajectories per scenario.

    Previous V4 ran 26-year simulation separately for EACH interpreter example.
    Now 2 trajectories per scenario yield up to 50 different annual windows;
    train scenarios S01–S16 and holdout S17–S20 never overlap.
    Real historical observations are never synthesized.
    """
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(seed)
    crisis_train_templates=catalog[:80];crisis_test_templates=catalog[80:]
    interpret_train_scenarios=scenarios[:16];interpret_test_scenarios=scenarios[16:]
    specs=[('crisis',n_crisis,crisis_train_templates,crisis_test_templates),
           ('interpreter',n_interpret,interpret_train_scenarios,interpret_test_scenarios)]
    counts={kind:{'train':max(8,int(n*.85)),'holdout':max(8,n-int(n*.85))} for kind,n,_,_ in specs}
    total=sum(sum(splits.values()) for splits in counts.values())
    processed=0;start=time.monotonic();cache={};simulations=0;report={}
    def notify(desc,force=False):
        if progress_callback:
            progress_callback(processed/total,desc,{'completed':processed,'total':total,
                              'simulations':simulations,'cache_size':len(cache),'elapsed_sec':round(time.monotonic()-start,1)})
    notify('Начинаем генерацию учебных примеров')
    for kind,n,train_refs,test_refs in specs:
        records={}
        for split,refs in [('train',train_refs),('holdout',test_refs)]:
            count=counts[kind][split];path=output/f'{kind}_{split}.jsonl'
            # Overwrite within this run; only complete rows are visible at any time.
            with path.open('w',encoding='utf-8') as f:
                for k in range(count):
                    item_seed=int(rng.integers(10000,2_000_000));ref=refs[k%len(refs)]
                    if kind=='crisis':
                        row=mk_crisis(k,item_seed,ref)
                    else:
                        # 2 fixed realizations per scenario, up to 50 unique year-windows each.
                        round_id=k//len(refs);replica=round_id%trajectory_variants
                        cache_key=(split,ref['scenario_id'],replica)
                        if cache_key not in cache:
                            scenario_idx=k%len(refs)
                            simulation_seed=int(seed+50_000+(0 if split=='train' else 100_000)+10_000*scenario_idx+replica*337)
                            notify(f'Сценарий {ref["scenario_id"]}: расчет траектории {replica+1}/{trajectory_variants}')
                            his,_=simulate(prep,models,world_report,actor,catalog,scenarios,
                                           seed=simulation_seed,horizon=26,
                                           scenario_id=ref['scenario_id'],crisis_mode='scenario',
                                           progress_callback=lambda f,year:notify(
                                            f'Сценарий {ref["scenario_id"]}: модельный год {year} · {replica+1}/{trajectory_variants}'))
                            if len(his)<2:raise RuntimeError('Simulation returned insufficient years')
                            cache[cache_key]=his;simulations+=1
                        his=cache[cache_key]
                        # Every scenario realization visits all year windows before repetition.
                        window_round=round_id//trajectory_variants
                        pos=1+(window_round%(len(his)-1))
                        row=mk_interpret(k,item_seed,prep,models,world_report,actor,catalog,scenarios,
                                         ref,history=his,pos=pos)
                    f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
                    processed+=1
                    if processed%8==0 or processed==total:
                        f.flush()
                        notify(f'{"Кризисы" if kind=="crisis" else "Интерпретации"} · {split}: {k+1}/{count}')
            records[split]=count
        report[kind]={**records,'holdout_family_disjoint':True,'training_samples_are_synthetic':True,
             'template_split':'80/20' if kind=='crisis' else '16/4'}
    report['performance']={'interpreter_unique_simulations':simulations,
        'naive_v4_simulations':counts['interpreter']['train']+counts['interpreter']['holdout'],
        'trajectory_variants_per_scenario':trajectory_variants,'elapsed_sec':round(time.monotonic()-start,2)}
    write_json(report,output/'corpus_manifest.json')
    notify('Все корпуса сохранены и проверены',True)
    return report

def parse_json_result(text):
    clean=text.strip().replace('```json','').replace('```','').strip()
    try:return json.loads(clean)
    except Exception:
        m=re.search(r'\{.*\}',clean,re.S)
        if m:
            try:return json.loads(m.group(0))
            except Exception:pass
    return None


def qlora_train(kind,corpus_dir,adapter_dir,model_name='Qwen/Qwen3-4B',max_steps=110,max_length=640,
                batch_accum=4,lr=1.5e-4,seed=42,validation_samples=6,progress_callback=None):
    """Requires a CUDA GPU (including L2 where supported), transformers, peft, bitsandbytes. Actually trains; refuses fake checkpoints."""
    if not torch.cuda.is_available():raise RuntimeError('QLoRA требует GPU CUDA. Выберите GPU (L2 или совместимый) в Colab.')
    from transformers import AutoTokenizer,AutoModelForCausalLM,BitsAndBytesConfig
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    seed_all(seed);corpus_dir=Path(corpus_dir);adapter_dir=Path(adapter_dir);adapter_dir.mkdir(parents=True,exist_ok=True)
    if progress_callback:progress_callback(0.0,'Загрузка базовой Qwen3-4B и подготовка QLoRA')
    train=[json.loads(t) for t in (corpus_dir/f'{kind}_train.jsonl').read_text().splitlines() if t.strip()]
    held=[json.loads(t) for t in (corpus_dir/f'{kind}_holdout.jsonl').read_text().splitlines() if t.strip()]
    tok=AutoTokenizer.from_pretrained(model_name,trust_remote_code=False)
    if tok.pad_token_id is None:tok.pad_token=tok.eos_token
    qconfig=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,
                                bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16)
    model=AutoModelForCausalLM.from_pretrained(model_name,quantization_config=qconfig,device_map={'':0},trust_remote_code=False)
    model.config.use_cache=False
    model=prepare_model_for_kbit_training(model,use_gradient_checkpointing=True)
    adapter_cfg=LoraConfig(r=8,lora_alpha=16,target_modules=['q_proj','v_proj'],lora_dropout=.05,bias='none',task_type='CAUSAL_LM')
    model=get_peft_model(model,adapter_cfg);model.train()
    if progress_callback:progress_callback(0.08,'Qwen загружена, начато обучение адаптера')
    opt=torch.optim.AdamW((p for p in model.parameters() if p.requires_grad),lr=lr,weight_decay=.01)
    def encode(item):
        system=('Ты модуль строго формализованного сценарного моделирования интеграционных процессов. '
                'Верни только JSON. Не выдавай синтетические сценарии за исторические факты. '
                'Соблюдай заданные границы параметров.' if kind=='crisis' else
                'Ты научный интерпретатор строго заданных результатов симуляции. Верни только JSON. '
                'Вычисления бери из входа; не придумывай числа, причинные связи или исторические факты.')
        prompt=tok.apply_chat_template([{'role':'system','content':system},
                 {'role':'user','content':json.dumps(item['prompt'],ensure_ascii=False)}],tokenize=False,add_generation_prompt=True,enable_thinking=False)
        answer=json.dumps(item['answer'],ensure_ascii=False,separators=(',',':'))+tok.eos_token
        a=tok(prompt,add_special_tokens=False)['input_ids']
        b=tok(answer,add_special_tokens=False)['input_ids']
        if len(b)>=max_length-64:raise ValueError('Слишком длинный целевой JSON')
        a=a[-(max_length-len(b)):];seq=a+b;labels=[-100]*len(a)+b
        return torch.tensor(seq,dtype=torch.long)[None].to('cuda'),torch.tensor(labels,dtype=torch.long)[None].to('cuda')
    history=[];start=time.time();opt.zero_grad(set_to_none=True)
    indices=np.arange(len(train));rng=np.random.default_rng(seed);rng.shuffle(indices);pos=0
    for step in range(max_steps):
        losses=[]
        for j in range(batch_accum):
            if pos>=len(indices):rng.shuffle(indices);pos=0
            item=train[int(indices[pos])];pos+=1
            x,y=encode(item)
            result=model(input_ids=x,labels=y,use_cache=False)
            loss=result.loss/batch_accum;loss.backward();losses.append(float(loss.detach())*batch_accum)
        torch.nn.utils.clip_grad_norm_((p for p in model.parameters() if p.requires_grad),1.)
        opt.step();opt.zero_grad(set_to_none=True)
        history.append({'step':step+1,'loss':float(np.mean(losses)),'elapsed_sec':round(time.time()-start,1)})
        if progress_callback and (step==0 or (step+1)%2==0 or step+1==max_steps):
            progress_callback(.08+.78*(step+1)/max_steps,f'Шаг {step+1}/{max_steps} · loss={np.mean(losses):.4f}')
    model.save_pretrained(adapter_dir,safe_serialization=True)
    model.eval()
    if progress_callback:progress_callback(.86,'Адаптер сохранён; отложенная проверка ответов')
    checks=[]
    for item in held[:validation_samples]:
        # Inference must supply *prompt only* to avoid validation leakage
        system=('Ты модуль строго формализованного сценарного моделирования интеграционных процессов. Верни только JSON. Не выдавай синтетические сценарии за исторические факты. Соблюдай заданные границы параметров.' if kind=='crisis' else
                'Ты научный интерпретатор строго заданных результатов симуляции. Верни только JSON. Вычисления бери из входа; не придумывай числа, причинные связи или исторические факты.')
        prompt=tok.apply_chat_template([{'role':'system','content':system},
                 {'role':'user','content':json.dumps(item['prompt'],ensure_ascii=False)}],tokenize=False,add_generation_prompt=True,enable_thinking=False)
        inp=tok(prompt,return_tensors='pt',truncation=True,max_length=max_length).to('cuda')
        with torch.inference_mode():
            gen=model.generate(**inp,max_new_tokens=224,do_sample=False,pad_token_id=tok.pad_token_id)
        generated=tok.decode(gen[0,inp.input_ids.shape[-1]:],skip_special_tokens=True)
        parsed=parse_json_result(generated)
        valid=isinstance(parsed,dict) and parsed.get('synthetic') is True
        if valid and kind=='crisis':
            s=parsed.get('shocks');valid=isinstance(s,list) and len(s)==4 and all(isinstance(v,(int,float)) and abs(v)<=2 for v in s)
        if valid and kind=='interpreter':
            try:valid=abs(float(parsed['mean_growth_pct'])-float(item['answer']['mean_growth_pct']))<.05 and abs(float(parsed['growth_change_pp'])-float(item['answer']['growth_change_pp']))<.05
            except (KeyError,TypeError,ValueError):valid=False
        checks.append({'id':item['id'],'valid':bool(valid),'generated':generated[:500]})
        if progress_callback:progress_callback(.86+.14*len(checks)/max(1,min(validation_samples,len(held))),
            f'Проверка {len(checks)}/{min(validation_samples,len(held))}')
    quality={'adapter':kind,'model':model_name,'steps':max_steps,'rank':8,'train_examples':len(train),'holdout_examples':len(held),
             'checked_holdout':len(checks),'passed':sum(int(v['valid']) for v in checks),
             'pass_rate':sum(v['valid'] for v in checks)/max(1,len(checks)),'train_duration_sec':round(time.time()-start,1),
             'training_complete':True,'quality_accepted':bool(checks) and all(t['valid'] for t in checks),
             'note':'Quality flag is independent from successful training. The holdout test never enters gradients.'}
    serialize(quality,adapter_dir/'quality.json');serialize(checks,adapter_dir/'heldout_examples.json')
    pd.DataFrame(history).to_csv(adapter_dir/'train_loss.csv',index=False)
    del opt,model;gc.collect();torch.cuda.empty_cache()
    return quality
