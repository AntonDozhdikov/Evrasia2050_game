#!/usr/bin/env python3
"""Build browser-replay data from immutable scientific V4.7 Stage3 handoff."""
import csv, io, json, hashlib, zipfile, pathlib, collections, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else pathlib.Path('/mnt/data/EURASIA_STAGE3_HANDOFF_V47.zip')
OUTPUT=ROOT/'assets'/'data.js'
COUNTRIES=['RUS','BLR','KAZ','KGZ','UZB','TJK','TKM','ARM']
S_FIELDS=['mean_growth_pct','trade_concentration','mean_reward','projects','agreements','projects_matured','projects_operating','trade_usd_total','network_strength','new_agreements','new_projects','capital_budget_total','project_cash_out','project_benefit_current','crises_active']
A_FIELDS=['trade','investment','coordination','resilience','partner_focus','labor_mobility']
H_FIELDS=['gdp_growth_pct','cpi_inflation_pct','investment_share_gdp','export_share_gdp','import_share_gdp','unemployment_pct','population_growth_pct','remittances_received_share_gdp','population_total','gdp_current_usd']

def cast(v):
    if v == '' or v is None: return None
    try:
        n=float(v)
        return int(n) if n.is_integer() else round(n,8)
    except ValueError: return v

with zipfile.ZipFile(SOURCE) as z:
    def csvfile(p):return list(csv.DictReader(io.StringIO(z.read(p).decode('utf-8-sig'))))
    scenarios=json.loads(z.read('runtime/metadata/scenarios_20.json'))
    contract=json.loads(z.read('runtime/integration_contract.json'))
    acceptance=json.loads(z.read('runtime/acceptance_v47.json'))
    trajectory=csvfile('runtime/scenario_trajectories_2025_2050.csv')
    agent=csvfile('runtime/agent_actions.csv')
    history=csvfile('runtime/game_input_tables/game_country_state.csv')
    dyads=csvfile('runtime/game_input_tables/game_dyads.csv')
    runs={}
    for r in trajectory:
        key='|'.join([r['scenario_id'],r['policy'],r['seed']]);obj=runs.setdefault(key,{'years':{},'actions':{}})
        year=int(r['year']);obj['years'][year]=[cast(r[k]) for k in S_FIELDS]
    for r in agent:
        key='|'.join([r['scenario_id'],r['policy'],r['seed']]);year=int(r['year']); obj=runs[key]
        obj['actions'].setdefault(year,{})[r['country']]=[cast(r[k]) for k in A_FIELDS]
    for key,run in runs.items():
        assert sorted(run['years'])==list(range(2025,2051)),key
        assert sorted(run['actions'])==list(range(2025,2051)),key
        run['years']=[run['years'][y] for y in range(2025,2051)]
        run['actions']=[[run['actions'][y][c] for c in COUNTRIES] for y in range(2025,2051)]
    historic={c:{} for c in COUNTRIES}
    for r in history:
        c=r['iso3']; year=r['year'];historic[c][year]={'v':[cast(r.get(k)) for k in H_FIELDS], 'observed':[int(r.get(k+'__observed','0') or '0') for k in H_FIELDS]}
    trade2024=[]
    for r in dyads:
        if int(r['year'])==2024 and r['reporter_iso3'] in COUNTRIES and r['partner_iso3'] in COUNTRIES:
            trade2024.append([r['reporter_iso3'],r['partner_iso3'],cast(r['bilateral_exports_usd']),int(r.get('bilateral_exports_usd__observed') or 0)])
    manifest={'source_file': SOURCE.name, 'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'source_stage1_sha256':acceptance['source_stage1_sha256'],'research_version':'V4.7',
        'scientific_ready': acceptance['scientific_ready'], 'technical_pass':acceptance['technical_pass'],
        'years':[2025,2050],'historical':[2000,2025], 'policies':['MAPPO_GREEDY','MAPPO','BARGAIN','NEUTRAL'],
        'seeds':[163,272,381], 'simulation': 'archived_replay_only', 'data_provenance':'V4.7 synthetic scenario outputs',
        'expected_runs':6240//26,'action_rows':49920,'scenario_rows':6240}
    db={'fields':S_FIELDS,'actionFields':A_FIELDS,'historyFields':H_FIELDS,'countries':COUNTRIES,'scenarios':scenarios,
        'history':historic,'trade2024':trade2024,'runs':runs,'manifest':manifest}
    assert len(runs)==240 and len(trajectory)==6240 and len(agent)==49920
    OUTPUT.write_text('/* Generated from the frozen Stage3 V4.7 artifact. Do not hand-edit. */\nwindow.EURASIA_DATA='+json.dumps(db,ensure_ascii=False,separators=(',',':'),allow_nan=False)+';\n',encoding='utf8')
    (ROOT/'research'/'results'/'SHA256_STAGE3_HANDOFF.txt').write_text(manifest['source_sha256']+'  '+SOURCE.name+'\n')
    (ROOT/'research'/'results'/'data_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    for path in ['runtime/scenario_trajectories_2025_2050.csv','runtime/agent_actions.csv','runtime/stress_test_metrics.csv','runtime/world/heldout_predictions.csv','runtime/acceptance_v47.json','runtime/integration_contract.json','runtime/marl/map_elites_manifest.json']:
        (ROOT/'research'/'results'/path.split('/')[-1]).write_bytes(z.read(path))
    for path in ['runtime/metadata/scenarios_20.json','runtime/metadata/crises_future_100.json']:
        (ROOT/'research'/'results'/path.split('/')[-1]).write_bytes(z.read(path))
    for path in [x for x in z.namelist() if x.startswith('src/') and not x.endswith('/')]:
        (ROOT/'research'/'v47_source'/path.split('/')[-1]).write_bytes(z.read(path))
    (ROOT/'research'/'results'/'source_SHA256.json').write_bytes(z.read('SHA256.json'))
    (ROOT/'docs'/'STAGE3_HANDOFF_SPEC.md').write_bytes(z.read('reports/STAGE3_HANDOFF_SPEC.md'))
    (ROOT/'docs'/'V47_ACCEPTANCE.md').write_bytes(z.read('reports/АКТ_ПРИЕМКИ_V47.md'))
    print('Built',OUTPUT,'bytes=',OUTPUT.stat().st_size,'runs=',len(runs),'history=',sum(map(len,historic.values())),'trade2024=',len(trade2024))
