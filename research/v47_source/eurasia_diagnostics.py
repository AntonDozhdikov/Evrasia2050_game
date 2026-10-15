"""Ten independent V4 diagnostic XLSX files. Only actual run artifacts, no invented metrics.
Portable, dependency-free XLSX (Office Open XML) writer for Colab.
"""
from pathlib import Path
import csv,json,math,re,zipfile,html
from xml.sax.saxutils import escape
import numpy as np

def read_rows(path,limit=20000):
 p=Path(path)
 if not p.exists():return [{'status':'NOT_EXECUTED_OR_NO_RESULT','file':str(path)}]
 if p.suffix=='.csv':
  with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))[:limit]
 if p.suffix=='.json':
  data=json.loads(p.read_text(encoding='utf-8'))
  if isinstance(data,list):return [x if isinstance(x,dict) else {'item':str(x)} for x in data][:limit]
  if isinstance(data,dict):return [{'key':k,'value':json.dumps(v,ensure_ascii=False,default=str) if isinstance(v,(dict,list)) else str(v)} for k,v in data.items()]
 return [{'file':str(p),'status':'unsupported_as_table'}]

def colname(k):
 s='';k+=1
 while k:s=chr(65+(k-1)%26)+s;k=(k-1)//26
 return s

def pack_xml(rows):
 keys=[]
 for r in rows:
  for k in r.keys():
   if k not in keys:keys.append(k)
 if not keys:keys=['status'];rows=[{'status':'no records'}]
 def cell(value,addr,style=0):
  value='' if value is None else value
  if isinstance(value,(int,float,np.integer,np.floating)) and not isinstance(value,bool) and math.isfinite(float(value)):
   return f'<c r="{addr}" s="{style}"><v>{float(value):.12g}</v></c>'
  s=escape(str(value))
  s=''.join(ch for ch in s if ord(ch)>=32 or ch in '\t\n')
  return f'<c r="{addr}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{s[:30000]}</t></is></c>'
 data=[]
 data.append('<row r="1" ht="27" customHeight="1">'+''.join(cell(k,f'{colname(j)}1',1) for j,k in enumerate(keys))+'</row>')
 for ix,r in enumerate(rows[:30000],start=2):
  data.append(f'<row r="{ix}">'+''.join(cell(r.get(k),f'{colname(j)}{ix}',0 if ix%2 else 2) for j,k in enumerate(keys))+'</row>')
 cols=''.join(f'<col min="{j+1}" max="{j+1}" width="{min(46,max(14,len(k)+5))}" customWidth="1"/>' for j,k in enumerate(keys))
 end=min(len(rows)+1,30001)
 return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:{colname(len(keys)-1)}{end}"/><sheetViews><sheetView tabSelected="1" workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>{cols}</cols><sheetData>'+''.join(data)+'</sheetData><autoFilter ref="A1:'+colname(len(keys)-1)+str(end)+'"/></worksheet>'

def write_xlsx(path,sheets):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 sheets=[(str(n)[:31],list(rows)) for n,rows in sheets]
 manifests=''.join(f'<sheet name="{escape(n)}" sheetId="{i+1}" r:id="rId{i+1}"/>' for i,(n,_) in enumerate(sheets))
 wb=f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{manifests}</sheets></workbook>'
 rels=''.join(f'<Relationship Id="rId{i+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i+1}.xml"/>' for i in range(len(sheets)))
 ctr=''.join(f'<Override PartName="/xl/worksheets/sheet{i+1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(len(sheets)))
 styles='<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="10"/><name val="Aptos"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="10"/><name val="Aptos"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF153A64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFEEF4FA"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="1" borderId="0" xfId="0" applyFont="1" applyFill="1"/><xf numFmtId="0" fontId="0" fillId="2" borderId="0" xfId="0" applyFill="1"/></cellXfs></styleSheet>'
 content_types='<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'+ctr+'</Types>'
 with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('[Content_Types].xml',content_types)
  z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
  z.writestr('xl/workbook.xml',wb)
  z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+rels+f'<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
  z.writestr('xl/styles.xml',styles)
  for i,(n,rows) in enumerate(sheets):z.writestr(f'xl/worksheets/sheet{i+1}.xml',pack_xml(rows))
 assert zipfile.ZipFile(path).testzip() is None
 return path

DIAG_NAMES={
 1:'01_HISTORICAL_MASKS',2:'02_WORLD_ENSEMBLE',3:'03_TRADE_NETWORK',4:'04_INTEGRATION_ECONOMY',
 5:'05_MARL_HETEROGENEITY',6:'06_REWARD_POLICY',7:'07_MAP_ELITES',8:'08_CRISIS_ENGINE',
 9:'09_OPTUNA_TEMPORAL',10:'10_SCIENTIFIC_ACCEPTANCE'}

def generate_all(out,source_dir=None):
 out=Path(out);dest=out/'diagnostics';dest.mkdir(exist_ok=True,parents=True)
 meta={'version':'V4.4','artifact_type':'actual_run_diagnostic','source':'computed_results_only',
       'note':'SMOKE means technical dry-run; do not interpret as scientific model acceptance'}
 def root(block,title):return [{'field':'block','value':block},{'field':'title','value':title}]+[{'field':k,'value':v} for k,v in meta.items()]
 specs={
 1:('Masked targets / real history',[('Источники',out/'input_data_audit.json'),('Исторические маски',out/'world_target_masks_initial.csv'),('Карантин',out/'quarantine_42_S05.csv')]),
 2:('World ensemble',[('Модели',out/'world'/'candidate_models.csv'),('По целям',out/'world'/'target_weights.csv'),('По показателям',out/'world'/'per_target_selection.csv'),('Тест',out/'world'/'heldout_predictions.csv'),('Метрики',out/'world'/'world_metrics.json')]),
 3:('Trade graph',[('Связи',out/'game_trade_network_2024.csv'),('Динамика',out/'scenario_trajectories_2025_2050.csv')]),
 4:('Institutions and budgets',[('Проекты',out/'integration_events.csv'),('Правила',out/'evolution'/'rule_proposals.csv'),('Экономика',out/'scenario_trajectories_2025_2050.csv')]),
 5:('MAPPO vs hetero comparator',[('MAPPO',out/'marl'/'mappo_history.csv'),('Гетерогенные',out/'marl'/'hetero_proxy_training.csv'),('Различия',out/'heterogeneity_comparison.csv')]),
 6:('Reward and action analysis',[('Политики',out/'policy_comparison.csv'),('Действия',out/'agent_actions.csv'),('Переговоры',out/'negotiation_controls.csv'),('Абляции',out/'ablation.csv')]),
 7:('Quality-diversity evolution',[('MAPElites',out/'marl'/'map_elites_archive.csv'),('ПроверкаПослеЭволюции',out/'marl'/'post_evolution_heldout.csv'),('Кандидаты',out/'marl'/'map_elites_trials.csv'),('Родословная',out/'marl'/'evolution_lineage.csv'),('Правила',out/'evolution'/'rule_proposals.csv')]),
 8:('Crises across full horizon',[('Стресс',out/'stress_test_metrics.csv'),('События',out/'crisis_event_log.csv'),('Календарь',out/'crisis_calendar.csv')]),
 9:('Optuna and temporal checks',[('Пробы',out/'world'/'optuna_trials.csv'),('Индивидуальный выбор',out/'world'/'per_target_selection.csv'),('Кандидаты',out/'world'/'candidate_models.csv'),('Погодовая проверка',out/'world'/'yearly_mse.csv')]),
 10:('Scientific acceptance',[('Приемка',out/'acceptance_v44.json'),('Сравнение',out/'policy_comparison.csv'),('Абляции',out/'ablation.csv'),('QLoRA',out/'qlora_quality.json')])}
 result=[]
 for i,(title,sheets) in specs.items():
  content=[('Паспорт',root(i,title))]+[(name,read_rows(path)) for name,path in sheets]
  file=dest/f'{DIAG_NAMES[i]}.xlsx';write_xlsx(file,content)
  result.append({'block':i,'filename':file.name,'size_bytes':file.stat().st_size,'sheets':len(content)})
 (dest/'diagnostics_manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 return result
