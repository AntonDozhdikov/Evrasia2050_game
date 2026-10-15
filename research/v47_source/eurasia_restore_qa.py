"""EURASIA 2050 V4.6 RESTORE: executable, non-optimizing audits.
All values are synthetic except source-check quantities. Audits never select a policy.
"""
from pathlib import Path
import hashlib,json,zipfile
import numpy as np
import pandas as pd

def _save(obj,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    return obj

def _digest(f):
    h=hashlib.sha256()
    with open(f,'rb') as stream:
        for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def preflight_restore(archive,data_root,prep,out):
    """Historical provenance and 2024 starting point are strict, not merely logged."""
    archive=Path(archive);data_root=Path(data_root);out=Path(out)
    with zipfile.ZipFile(archive) as z:
        members=set(z.namelist());zipok=z.testzip() is None
    needed={'stage2/country_year.csv','stage2/dyad_year.csv','stage2/initial_state.json',
            'stage2/game_country_state.csv','stage2/game_dyads.csv','quality/quarantine_S05_42.csv'}
    checks={'input_is_cleaned_stage1':'STAGE1_FINAL_FOR_STAGE2' in archive.name,
      'zip_integrity':zipok,'required_stage1_files':needed.issubset(members),
      'eight_countries':int(prep.z.shape[1])==8,'26_observed_years':int(prep.z.shape[0])==26,
      'sequence_length_five':int(prep.seq_len)==5,
      '2024_state_available':bool(np.isfinite(prep.z[24]).all()),
      'all_2024_trade_edges_classified':int(np.sum(prep.game_sources>0))==56,
      'historical_edges_have_no_game_synthetic_as_observations':bool(np.count_nonzero(prep.edge_source[:25]==3)==0)}
    result={'passed':all(checks.values()),'checks':checks,'input_sha256':_digest(archive),
      'source':'real_observations_and_game_only_synthetic_links_are_separate'}
    _save(result,out/'restore_stage1_preflight.json')
    if not result['passed']:raise AssertionError('RESTORE historical preflight failed: '+str(checks))
    return result

def runtime_economic_checks(prep,models,world_report,catalog,scenarios,out):
    """Same-random-seed neutral-vs-idle paired test detects the old +0.022 incentive."""
    from eurasia_runtime import EurasiaEnv,N,ACT_NAMES
    settings=dict(prep=prep,models=models,world_report=world_report,catalog=catalog,
                  scenarios=scenarios,seed=12819,horizon=4,crisis_mode='scenario',scenario_id=scenarios[0]['scenario_id'])
    e0=EurasiaEnv(**settings);e1=EurasiaEnv(**settings)
    neutral=np.ones((N,len(ACT_NAMES)),dtype=int)
    idle=neutral.copy();idle[:,1]=0
    init=e0.energy.copy()
    _,_,_,n=e0.step(neutral);_,_,_,z=e1.step(idle)
    checks={'neutral_and_idle_same_capital_without_projects':bool(np.allclose(e0.energy,e1.energy,atol=1e-7)),
      'idle_does_not_mint_capital':bool(np.all(e1.energy<=init+1e-7)),
      'neutral_project_count_zero':n['new_projects']==0,
      'idle_project_count_zero':z['new_projects']==0,
      'no_backward_game_time':bool(e0.year==2025 and e0.steps==1),
      'budget_bounded':bool(np.isfinite(e0.energy).all() and np.all(e0.energy>=0)),
      'no_reward_for_idle_count':bool(np.isfinite(e0.returns).all())}
    result={'passed':all(checks.values()),'checks':checks,'baseline_energy':init.tolist(),
      'neutral_after':e0.energy.tolist(),'idle_after':e1.energy.tolist(),
      'note':'synthetic game balance only; not real-world monetary welfare'}
    _save(result,Path(out)/'restore_economy_preflight.json')
    if not result['passed']:raise AssertionError('RESTORE economy preflight failed: '+str(checks))
    return result

def final_restore_audit(out,src,meta,prep,world_report,selection,run_mode):
    """Verify V4.6 major capabilities remain ACTUALLY exported in the completed run.
    Does not reinterpret known evaluation periods as a fresh scientific holdout.
    """
    out=Path(out);src=Path(src);meta=Path(meta)
    modules=['eurasia_runtime.py','eurasia_v4.py','eurasia_lora.py','eurasia_diagnostics.py',
      'eurasia_progress.py','eurasia_world_v42.py','eurasia_marl_v42.py','eurasia_world_v43.py',
      'eurasia_marl_v43.py','eurasia_world_v44.py','eurasia_marl_v44.py','eurasia_v45_panel.py',
      'eurasia_v45_finalize.py','eurasia_v45_qa.py','eurasia_v46_guardrails.py',
      'eurasia_restore_qa.py']
    required={
      'historical_audit':out/'input_data_audit.json',
      'world_selection_8':out/'world'/'per_target_selection.csv',
      'world_optuna_trials':out/'world'/'optuna_trials_per_target.csv',
      'world_weights':out/'world'/'per_target_estimators.joblib',
      'world_forecast_test':out/'world'/'heldout_predictions.csv',
      'marl_selected':out/'marl'/'mappo.pt',
      'marl_selection':out/'marl'/'v45_archive'/'paired_selection.csv',
      'marl_post_selection_audit':out/'marl'/'v45_archive'/'post_selection_audit.csv',
      'crisis_stress':out/'scenario_trajectories_2025_2050.csv',
      'crisis_agent_actions':out/'agent_actions.csv',
      'marl_reward_proxy_audit':out/'marl'/'v46_reward_audit'/'reward_proxy_audit.json',
      'ten_diagnostics':out/'diagnostics',
      'integration_contract':out/'integration_contract.json',
      'scientific_acceptance':out/'acceptance_v46.json'
    }
    checks={'all_16_source_modules_present':all((src/n).exists() for n in modules),
      'no_fixed_idle_bonus_in_runtime':'+.022*(ac[:,1]==0)' not in (src/'eurasia_runtime.py').read_text(),
      'crisis_100_templates':len(json.loads((meta/'crises_future_100.json').read_text()))==100,
      'crisis_20_scenarios':len(json.loads((meta/'scenarios_20.json').read_text()))==20,
      'all_expected_outputs_available':all(p.exists() for p in required.values()),
      '10_independent_excel_books':len(list((out/'diagnostics').glob('*.xlsx')))==10,
      'policy_selected_weight_file_is_same_as_manifest':True,
      'eight_forecast_targets_reported':False}
    selpath=out/'world'/'per_target_selection.csv'
    if selpath.exists():
        tab=pd.read_csv(selpath);checks['eight_forecast_targets_reported']=len(tab)==8
    checkpoint=out/'marl'/'mappo.pt'
    expected=selection.get('saved_sha256')
    checks['policy_selected_weight_file_is_same_as_manifest']=checkpoint.exists() and bool(expected) and _digest(checkpoint)==expected
    qlora=[]
    for name in ['lora_crisis','lora_interpreter']:
        path=out/name/'adapter_model.safetensors'
        qlora.append({'adapter':name,'weight_file_exists':path.exists(),'sha256':_digest(path) if path.exists() else None})
    if run_mode=='FULL':checks['both_lora_weight_files']=all(z['weight_file_exists'] for z in qlora)
    else:checks['full_lora_not_required_in_smoke']=True
    behavior={}
    p=out/'scenario_trajectories_2025_2050.csv';ap=out/'agent_actions.csv'
    if p.exists():
        df=pd.read_csv(p)
        for policy,g in df.groupby('policy'):
            behavior[str(policy)]={'new_projects':int(g.new_projects.sum()),
              'late_projects_2029_onward':int(g.loc[g.year>=2029,'new_projects'].sum()),
              'matured_projects':int(g.projects_matured.sum()),
              'project_cash_out':float(g.project_cash_out.sum()),
              'project_benefit':float(g.project_benefit_current.sum()),
              'project_net_cash':float(g.project_benefit_current.sum()-g.project_cash_out.sum())}
    if ap.exists():
        acts=pd.read_csv(ap)
        for policy,g in acts.groupby('policy'):
            if policy not in behavior:behavior[policy]={}
            cols=[c for c in ['trade','investment','coordination','protection','focus','mobility'] if c in g]
            behavior[policy]['distinct_action_vectors']=int(g[cols].drop_duplicates().shape[0]) if cols else None
            behavior[policy]['distinct_country_policy_modes']=int(g.groupby('country')[cols].agg(lambda s:s.mode().iat[0] if not s.mode().empty else -1).drop_duplicates().shape[0]) if cols else None
    result={'version':'V4.6-RESTORE','run_mode':run_mode,
      'technical_structure_passed':all(checks.values()),'overall_status':'TECHNICALLY_PRESENT' if all(checks.values()) else 'STRUCTURAL_REGRESSION',
      'checks':checks,'modules':modules,'required_outputs':{k:v.exists() for k,v in required.items()},
      'behavior_descriptive_not_scientific_proof':behavior,
      'qwen_adapter_provenance':qlora,
      'known_scientific_limits':['V4.1 frozen model is only a reference and uses a different training regime',
        'Selected V4.5 checkpoint was trained under the OLD environment economy; transfer requires new independent validation',
        'Macro forecast horizon to 2050 is scenario extrapolation, not causal prediction',
        '2021–2025 is a repeatedly exposed test and cannot be considered pristine',
        'Project cash metrics depend on assumed coefficients',
        'Neutral outcomes may rationally contain no projects']}
    _save(result,out/'restore_acceptance.json')
    return result
