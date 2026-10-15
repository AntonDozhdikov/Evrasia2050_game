"""Eurasia 2050 V4.5: protected checkpoints, paired policy promotion and crisis audit.

Historical inputs are unchanged. The policy candidate bank is frozen before the
selection and evaluation stages. No scalar prize is given for signing an agreement.
DGM inspiration is restricted to declarative policy-gate configurations.
"""
from __future__ import annotations
import hashlib, json, shutil, math
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from eurasia_runtime import simulate, write_json, ACT_NAMES
from eurasia_marl_v44 import EvoActor44, load_marl_v44


def filehash(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):h.update(chunk)
    return h.hexdigest()


def extract_reference(payload, output):
    import zlib, base64
    dst=Path(output);dst.parent.mkdir(parents=True,exist_ok=True)
    raw=zlib.decompress(base64.b85decode(payload))
    dst.write_bytes(raw)
    ck=torch.load(dst,map_location='cpu',weights_only=True)
    if ck.get('version')!=44 or 'evolution_gates' not in ck:
        raise RuntimeError('Invalid V4.5 frozen policy: requires audited V4.4-compatible checkpoint')
    a,_=load_marl_v44(dst)
    if a.evolution_gates.shape!=(4,8,len(ACT_NAMES),3):raise RuntimeError('Gate shape mismatch')
    return dst


def _row(prep, models, world, actor, crises, scenarios, seed, sid, years=26):
    h,r=simulate(prep,models,world,actor,crises,scenarios,
        seed=int(seed),policy='MAPPO',horizon=years,
        scenario_id=sid,crisis_mode='scenario',sample_actions=False)
    return {
        'scenario_id':str(sid),'seed':int(seed),
        'reward':float(np.mean(r)),
        'projects':int(sum(z['new_projects'] for z in h)),
        'agreements':int(sum(z['new_agreements'] for z in h)),
        'matured':int(sum(z['projects_matured'] for z in h)),
        'late_projects':int(sum(z['new_projects'] for z in h if z['year']>=2029)),
        'project_years':int(len({z['year'] for z in h if z['new_projects']>0})),
        'cash_out':float(sum(z['project_cash_out'] for z in h)),
        'project_benefit':float(sum(z['project_benefit_current'] for z in h)),
        'net_project_cash':float(sum(z['project_benefit_current']-z['project_cash_out'] for z in h)),
        'mean_growth':float(np.mean([z['mean_growth_pct'] for z in h])),
        'economic_score':float(0.60*(sum(z['project_benefit_current']-z['project_cash_out'] for z in h)/(8.0*years))+
                               0.04*np.mean([z['mean_growth_pct'] for z in h])),
        'action_trace':np.asarray([z['actions'] for z in h],np.int8),
    }


def _evaluate(prep,models,world,candidate,crises,scenarios,sids,seeds,horizon,label):
    res=[]; traces={}
    for sid in sids:
        for seed in seeds:
            o=_row(prep,models,world,candidate,crises,scenarios,seed,sid,horizon)
            traces[(str(sid),int(seed))]=o.pop('action_trace')
            res.append({'candidate':label,**o})
    return pd.DataFrame(res),traces


def _diff(candidate,reference):
    fields=['reward','economic_score','projects','agreements','matured','late_projects','net_project_cash','cash_out','project_benefit','mean_growth']
    a=candidate.set_index(['scenario_id','seed']).sort_index()
    b=reference.set_index(['scenario_id','seed']).sort_index()
    if not a.index.equals(b.index):raise RuntimeError('Paired evaluation is not aligned')
    return (a[fields]-b[fields]).reset_index()


def _safe_checkpoint(actor, template, dest, refsha):
    ck=torch.load(template,map_location='cpu',weights_only=True)
    ck['actor']={k:v.detach().cpu().clone() for k,v in actor.base.state_dict().items()}
    ck['evolution_gates']=actor.evolution_gates.detach().cpu().clone()
    ck['version']=44
    ck['algo']='V45_MAPPO_CTDE_PAIRED_ELITE_DGM_CONFIG_ONLY'
    ck['selected_variant']='V45_PAIRED_PROMOTED'
    ck['v45_baseline_sha256']=refsha
    torch.save(ck,dest)
    reloaded,_=load_marl_v44(dest)
    for k,v in actor.base.state_dict().items():
        if not torch.equal(v.cpu(),reloaded.base.state_dict()[k].cpu()):
            raise RuntimeError('Checkpoint base actor reload mismatch')
    if not torch.equal(reloaded.evolution_gates.cpu(),actor.evolution_gates.cpu()):
        raise RuntimeError('Checkpoint gate reload mismatch')
    return reloaded


def finalize_policy(prep,models,world,new_candidate,crises,scenarios,model_dir,frozen_path,mode='FULL',seed=45,progress=None):
    out=Path(model_dir);out.mkdir(parents=True,exist_ok=True)
    if not (out/'mappo.pt').exists():raise FileNotFoundError('V4.4 current mappo.pt missing')
    archive=out/'v45_archive';archive.mkdir(exist_ok=True)
    shutil.copy2(out/'mappo.pt',archive/'fresh_post_evolution_v44.pt')
    reference,_=load_marl_v44(frozen_path)
    srcsha=filehash(frozen_path)
    fresh_sha=filehash(archive/'fresh_post_evolution_v44.pt')
    # Additional archived candidate is already a policy with state-dependent economic/crisis gates.
    bank={'FROZEN_STAGE1':reference,'FRESH_V44_QD':new_candidate}
    # Never choose using post-selection audit cases. Scenario IDs are locked first.
    ids=[s['scenario_id'] for s in scenarios]
    if len(ids)<10:raise RuntimeError('Expected 20 crisis scenarios')
    selection_ids=[ids[k] for k in ([0,2,4,6,8] if mode=='FULL' else [0,2])]
    audit_ids=[ids[k] for k in ([11,13,15,17,19] if mode=='FULL' else [11])]
    selection_seeds=[seed+220,seed+301,seed+421] if mode=='FULL' else [seed+220]
    audit_seeds=[seed+1040,seed+1180,seed+1300] if mode=='FULL' else [seed+1040]
    horizon=26 if mode=='FULL' else 7
    protocol={'version':'V4.5','mode':mode,'candidate_bank_locked':list(bank),
        'selection_scenarios':selection_ids,'selection_seeds':selection_seeds,
        'audit_scenarios':audit_ids,'audit_seeds':audit_seeds,
        'horizon':horizon,'frozen_candidate_sha256':srcsha,
        'fresh_candidate_sha256':fresh_sha,
        'post_selection_never_changes_winner':True,
        'audit_status':'REUSED_SYNTHETIC_SCENARIO_CATALOG_NOT_PRISTINE_HOLDOUT',
        'policy_objective':'0.60*(realized project benefits minus project expenses)/(8*horizon) + 0.04*mean GDP growth (scenario assumptions)',
        'promote_rule':'select greater paired mean economic score, no mandatory projects or artificial activity bonuses; keep random scenario pairing, report uncertainty and benchmarks; old frozen candidate is legacy control not scientific ground truth'}
    write_json(protocol,archive/'selection_protocol_precommit.json')
    rows={};traces={}
    for ix,(label,actor) in enumerate(bank.items()):
        rows[label],traces[label]=_evaluate(prep,models,world,actor,crises,scenarios,
            selection_ids,selection_seeds,horizon,label)
        if progress:progress((ix+1)/len(bank),f'V4.5 selection: {label}')
    df=pd.concat(rows.values(),ignore_index=True)
    df.to_csv(archive/'paired_selection.csv',index=False)
    paired=_diff(rows['FRESH_V44_QD'],rows['FROZEN_STAGE1'])
    paired.to_csv(archive/'paired_differences.csv',index=False)
    means={label:{k:float(v[k].mean()) for k in ['reward','economic_score','projects','matured','late_projects','net_project_cash','cash_out','mean_growth']} for label,v in rows.items()}
    # V4.7: precommitted independent economic proxy. Never force an agreement or project.
    # Raw native reward is a diagnostic, not the policy promotion criterion.
    delta_score=float(paired.economic_score.mean())
    finite=bool(np.isfinite(paired.economic_score.to_numpy()).all())
    admit_fresh=bool(finite and delta_score>0.)
    proxy_only_gain=bool(float(paired.reward.mean())>0 and delta_score<=0.)
    # Scenario-cluster bootstrap is *descriptive*, not a newly pristine scientific holdout.
    grouped=paired.groupby('scenario_id').economic_score.mean().to_numpy()
    ci_low,ci_high=(None,None)
    if len(grouped)>1:
        rng=np.random.default_rng(seed+4791)
        draw=rng.choice(grouped,size=(3000,len(grouped)),replace=True).mean(axis=1)
        ci_low,ci_high=[float(x) for x in np.quantile(draw,[.025,.975])]
    uncertainty={'scenario_cluster_bootstrap_95pct':[ci_low,ci_high],
                 'paired_mean_economic_score':delta_score,
                 'selected_on_audit_data':False,
                 'confidence_interval_is_not_causal_evidence':True}
    write_json(uncertainty,archive/'selection_uncertainty.json')
    winner='FRESH_V44_QD' if admit_fresh else 'FROZEN_STAGE1'
    # Both contenders are scientifically unaccepted: this selection only protects runtime behaviour.
    winning_actor=bank[winner]
    saved=_safe_checkpoint(winning_actor,archive/'fresh_post_evolution_v44.pt',out/'mappo.pt',srcsha)
    # Separate immutable checkpoint of preselected reference and promoted winner.
    shutil.copy2(frozen_path,archive/'frozen_stage1_immutable.pt')
    shutil.copy2(out/'mappo.pt',archive/'selected_policy_v45.pt')
    conf={'version':'V4.5','format':'declarative_gates_only','selected':winner,
          'base_checkpoint_sha256':filehash(out/'mappo.pt'),
          'frozen_baseline_sha256':srcsha,
          'gates':saved.evolution_gates.detach().cpu().numpy().tolist(),
          'observation_features':['bias','previous_crisis_intensity','capital_shortage','elapsed_time'],
          'no_code_mutation':True,'no_auto_rule_rewrite':True}
    write_json(conf,archive/'selected_declarative_config.json')
    # Audit cases are not used to change the selected policy; same initial conditions.
    aud=[];tr={}
    for label,actor in [('V45_SELECTED',saved),('FROZEN_STAGE1',reference)]:
        dd,trace=_evaluate(prep,models,world,actor,crises,scenarios,audit_ids,audit_seeds,horizon,label)
        aud.append(dd);tr[label]=trace
    audit=pd.concat(aud,ignore_index=True);audit.to_csv(archive/'post_selection_audit.csv',index=False)
    auddiff=_diff(audit[audit.candidate=='V45_SELECTED'],audit[audit.candidate=='FROZEN_STAGE1'])
    auddiff.to_csv(archive/'post_selection_paired_deltas.csv',index=False)
    # Crisis-action response vs economic response, recorded separately.
    response=[]
    for seed0 in audit_seeds:
        base_trace=tr['V45_SELECTED'][(audit_ids[0],seed0)]
        for sid in audit_ids[1:]:
            alt=tr['V45_SELECTED'][(sid,seed0)]
            aa=audit[(audit.candidate=='V45_SELECTED')&(audit.seed==seed0)&(audit.scenario_id==audit_ids[0])].iloc[0]
            bb=audit[(audit.candidate=='V45_SELECTED')&(audit.seed==seed0)&(audit.scenario_id==sid)].iloc[0]
            response.append({'seed':seed0,'base_scenario':audit_ids[0],'crisis_scenario':sid,
             'action_change_fraction':float(np.mean(base_trace!=alt)),
             'reward_difference':float(bb.reward-aa.reward),
             'net_project_difference':float(bb.net_project_cash-aa.net_project_cash)})
    pd.DataFrame(response,columns=['seed','base_scenario','crisis_scenario','action_change_fraction','reward_difference','net_project_difference']).to_csv(archive/'crisis_response.csv',index=False)
    # Independent baseline report: benchmarks are NOT used to replace the locked candidate list.
    # All choices and the random seeds have been committed before this comparison.
    baseline_records=[]
    for policy in ('BARGAIN','NEUTRAL'):
        for sid in audit_ids:
            for seed0 in audit_seeds:
                h,ret=simulate(prep,models,world,None,crises,scenarios,seed=int(seed0),
                               policy=policy,horizon=horizon,scenario_id=sid,crisis_mode='scenario')
                net=float(sum(z['project_benefit_current']-z['project_cash_out'] for z in h))
                growth=float(np.mean([z['mean_growth_pct'] for z in h]))
                baseline_records.append({'policy':policy,'scenario_id':sid,'seed':seed0,
                   'economic_score':.60*net/(8*horizon)+.04*growth,
                   'native_reward':float(np.mean(ret)),
                   'net_project_cash':net,
                   'new_projects':int(sum(z['new_projects'] for z in h))})
    pd.DataFrame(baseline_records).to_csv(archive/'independent_economic_baselines.csv',index=False)
    metrics={'version':'V4.7','mode':mode,'selection_winner':winner,'economic_selection':uncertainty,'selection_metric':'paired_economic_score_not_native_reward','new_candidate_admitted':bool(admit_fresh),'blocked_reward_proxy_only_gain':bool(proxy_only_gain),
          'selection_means':means,'post_selection_delta_reward':float(auddiff.reward.mean()),
          'post_selection_delta_net_project_cash':float(auddiff.net_project_cash.mean()),
          'post_selection_mean_projects':float(audit[audit.candidate=='V45_SELECTED'].projects.mean()),
          'post_selection_late_projects':float(audit[audit.candidate=='V45_SELECTED'].late_projects.mean()),
          'post_selection_crisis_action_distance':float(np.mean([r['action_change_fraction'] for r in response])) if response else None,
          'saved_sha256':filehash(out/'mappo.pt'),
          'precommitted_audit':True,'scientifically_accepted':False,
          'limitations':'Numerical game reward and synthetic-project cash are not empirically identified welfare or causal integration effects.'}
    write_json(metrics,archive/'promotion_manifest.json')
    return saved,metrics
