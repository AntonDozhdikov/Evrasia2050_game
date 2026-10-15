"""V4.1: one live dashboard shared across notebook cells, no per-sample log spam."""
from pathlib import Path
import json,time,html
from datetime import datetime,timezone
try:
 import ipywidgets as widgets
 from IPython.display import display
 WIDGETS_AVAILABLE=True
except ImportError:
 WIDGETS_AVAILABLE=False
 from IPython.display import display,HTML

PHASES=[
 ('setup','Подготовка среды и архива',5),
 ('world','World Model / Optuna / сравнение моделей',18),
 ('marl','MAPPO, гетерогенные агенты и MAP-Elites',22),
 ('policy','Сравнение стратегий и эволюция правил',5),
 ('stress','100 кризисов и 20 стресс-сценариев',9),
 ('ablation','Абляционные эксперименты',3),
 ('corpus','Генерация корпусов Qwen с кэшем траекторий',16),
 ('crisis_lora','QLoRA A — генератор кризисов',10),
 ('interpret_lora','QLoRA B — научный интерпретатор',9),
 ('finish','Научная приемка, диагностики, архивы',3),
]
assert sum(w for _,_,w in PHASES)==100

def fmt_time(seconds):
 if seconds is None:return '—'
 seconds=max(0,int(seconds))
 h,r=divmod(seconds,3600);m,s=divmod(r,60)
 return f'{h:02d}:{m:02d}:{s:02d}'

class TrainingDashboard:
 def __init__(self,out,mode='FULL',throttle_seconds=.55):
  self.out=Path(out);self.out.mkdir(parents=True,exist_ok=True)
  self.mode=mode;self.start_time=time.monotonic();self.started_at=datetime.now(timezone.utc).isoformat()
  self.phase_times={};self.phase=None;self.fraction=0.;self.description='Подготовка';self.finished=set()
  self.last_render=0.;self.last_write=0.;self.throttle=float(throttle_seconds);self._shown=False
  self.weights={name:w for name,_,w in PHASES};self.index={name:i for i,(name,_,_) in enumerate(PHASES)}
  self.title={name:title for name,title,_ in PHASES}
  if WIDGETS_AVAILABLE:
   self.header=widgets.HTML()
   self.totalbar=widgets.IntProgress(value=0,min=0,max=1000,description='Общий',bar_style='info',layout=widgets.Layout(width='98%'))
   self.stagebar=widgets.IntProgress(value=0,min=0,max=1000,description='Этап',bar_style='info',layout=widgets.Layout(width='98%'))
   self.details=widgets.HTML()
   self.panel=widgets.VBox([self.header,self.totalbar,self.stagebar,self.details],
               layout=widgets.Layout(border='1px solid #c7d7e5',padding='10px',width='99%'))
  else:self.panel=None;self.display_handle=None
 def show(self):
  if self.panel is not None:display(self.panel)
  elif not self._shown:
   self.display_handle=display(HTML('<b>Евразия 2050 · V4.1</b>'),display_id=True);self._shown=True
  self.render(force=True)
 def _overall(self):
  if self.phase is None:return 0.
  idx=self.index[self.phase]
  return sum(PHASES[i][2] for i in range(idx))+self.weights[self.phase]*self.fraction
 def begin(self,name,description=None):
  if name not in self.index:raise KeyError(name)
  if self.phase and name!=self.phase and self.phase not in self.finished:
   self.finished.add(self.phase)
  self.phase=name;self.phase_times[name]=time.monotonic();self.fraction=0.
  self.description=description or self.title[name]
  self.render(force=True)
 def update(self,fraction,description=None,stats=None):
  self.fraction=max(self.fraction,min(1.,max(0.,float(fraction))))
  if description:self.description=str(description)
  if stats:self.stats=stats
  self.render()
 def complete(self,description='Завершено'):
  self.fraction=1.;self.description=description
  if self.phase:self.finished.add(self.phase)
  self.render(force=True)
 def skip(self,name,description='Пропущено (SMOKE)'):
  self.begin(name,description);self.complete(description)
 def _snapshot(self):
  elapsed=time.monotonic()-self.start_time
  pelapsed=time.monotonic()-self.phase_times.get(self.phase,self.start_time)
  eta=pelapsed*(1-self.fraction)/self.fraction if .02<self.fraction<1. else (0. if self.fraction>=1. else None)
  return {'version':'V4.1','mode':self.mode,'phase':self.phase,'stage':self.title.get(self.phase,''),
          'description':self.description,'phase_fraction':round(self.fraction,5),
          'overall_percent':round(self._overall(),2),'elapsed_seconds':round(elapsed,1),
          'phase_elapsed_seconds':round(pelapsed,1),'phase_eta_est_seconds':round(eta,1) if eta is not None else None,
          'completed_phases':sorted(self.finished),'started_at_utc':self.started_at,
          'updated_at_utc':datetime.now(timezone.utc).isoformat(),
          'stats':getattr(self,'stats',{})}
 def render(self,force=False):
  now=time.monotonic()
  if not force and now-self.last_render<self.throttle:return
  self.last_render=now
  d=self._snapshot();idx=self.index.get(self.phase,0)+1
  if self.panel is not None:
   self.totalbar.value=int(round(d['overall_percent']*10))
   self.stagebar.value=int(round(self.fraction*1000))
   self.header.value=(f'<b>ЕВРАЗИЯ 2050 — Обучение V4.1</b> · '+
       f'Этап {idx}/{len(PHASES)}: {html.escape(d["stage"])}')
   self.details.value=(f'<div style="font-size:13px;line-height:1.6">'+
       f'<b>{d["overall_percent"]:.1f}% всего</b> · {self.fraction*100:.1f}% этапа · '+
       f'Прошло {fmt_time(d["elapsed_seconds"])} · '+
       f'До конца этапа ≈ {fmt_time(d["phase_eta_est_seconds"])}'+
       f'<div style="color:#56687a">{html.escape(self.description)}</div></div>')
  elif self.display_handle is not None:
   try:self.display_handle.update(HTML(f'<b>V4.1 {d["overall_percent"]:.1f}%</b> — {html.escape(self.description)} · {fmt_time(d["elapsed_seconds"])}'))
   except Exception:pass
  if force or now-self.last_write>4:
   tmp=self.out/'progress_status.json.tmp';dest=self.out/'progress_status.json'
   tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(dest)
   self.last_write=now
