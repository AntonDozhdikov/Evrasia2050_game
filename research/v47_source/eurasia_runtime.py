"""EURASIA 2050 V4.2. Research + executable game runtime. No synthetic historical records.
World predictions trained on observed transitions only; scenario intervention coefficients
are explicit structural assumptions, not identified causal effects.
"""
from __future__ import annotations
import json, math, random, time, hashlib, zipfile, copy, os
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.distributions import Categorical

COUNTRIES=['RUS','BLR','KAZ','KGZ','UZB','TJK','TKM','ARM'];N=8
FEATURES=['agriculture_value_added_pct','cpi_inflation_pct','current_account_share_gdp','export_share_gdp',
'fdi_net_share_gdp','gdp_current_usd','gdp_growth_pct','gdp_per_capita_usd','import_share_gdp',
'industry_value_added_pct','investment_share_gdp','manufacturing_value_added_pct','population_15_64_pct',
'population_growth_pct','population_total','remittances_received_share_gdp','unemployment_pct']
TARGETS=['gdp_growth_pct','cpi_inflation_pct','investment_share_gdp','export_share_gdp',
'import_share_gdp','unemployment_pct','population_growth_pct','remittances_received_share_gdp']
GLOB=['gas_price_usd','global_gdp_growth_pct','metals_price','oil_price_usd']
INSTITUTIONS=['eaeu_member','union_state_member','common_labor_market','customs_code_2018']
ACT_NAMES=['trade','investment','coordination','resilience','partner_focus','labor_mobility']
ACT_LABELS={
 'trade':['диверсифицировать','сохранить условия','углубить региональную торговлю'],
 'investment':['накопить резервы','инвестировать умеренно','крупный совместный проект'],
 'coordination':['сохранить автономию','переговоры','институциональная инициатива'],
 'resilience':['минимальная защита','умеренная защита','активная защита'],
 'partner_focus':['внешние рынки','существующие партнеры','региональные партнерства'],
 'labor_mobility':['сохранить ограничения','сохранить условия','развивать согласованную мобильность']}
LOG_FEATS={'gdp_current_usd','population_total','gdp_per_capita_usd'}
BOUNDS={'gdp_growth_pct':(-18,25),'cpi_inflation_pct':(-5,70),'investment_share_gdp':(0,70),
'export_share_gdp':(0,140),'import_share_gdp':(0,140),'unemployment_pct':(0,45),
'population_growth_pct':(-5,8),'remittances_received_share_gdp':(0,65)}


def seed_all(seed=42):
 random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
 if torch.cuda.is_available():torch.cuda.manual_seed_all(seed)
def write_json(obj,path):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False,default=lambda v:v.item() if isinstance(v,np.generic) else str(v)),encoding='utf-8')
def sha256(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
 return h.hexdigest()
def extract_safe(path,target):
 target=Path(target).resolve();target.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(path) as z:
  for m in z.infolist():
   p=(target/m.filename).resolve()
   if target not in p.parents and target!=p:raise ValueError('unsafe ZIP path')
   if m.file_size>300_000_000:raise ValueError('oversized ZIP member')
  z.extractall(target)
 return target
def detect_root(root):
 root=Path(root)
 for parent in [root]+[x for x in root.rglob('*') if x.is_dir()]:
  if (parent/'game_country_state.csv').exists():return parent,parent.parent
  if (parent/'tables/game_country_state.csv').exists():return parent/'tables',parent
  if (parent/'stage2/game_country_state.csv').exists():return parent/'stage2',parent
  if (parent/'game_input_tables/game_country_state.csv').exists():return parent/'game_input_tables',parent
 raise FileNotFoundError('Не найден tables/game_country_state.csv или stage2/game_country_state.csv')
def load_bundle(root):
 base,parent=detect_root(root);tables={}
 for n in ['game_country_state','game_dyads','game_global','dyad_year','country_year','institution_year']:
  p=base/(n+'.csv');tables[n]=pd.read_csv(p,low_memory=False) if p.exists() else pd.DataFrame()
 c=tables['game_country_state'];d=tables['game_dyads'];g=tables['game_global']
 for frame,keys in [(c,['iso3','year']),(d,['reporter_iso3','partner_iso3','year']),(g,['year'])]:
  if frame.empty or frame.duplicated(keys).any():raise ValueError('Нет данных / дубли: '+str(keys))
 if set(c.iso3)!=set(COUNTRIES):raise ValueError('Неверный состав восьми государств')
 for f in FEATURES+INSTITUTIONS:
  if f not in c:raise ValueError('Отсутствует: '+f)
 for f in ['bilateral_exports_usd','bilateral_exports_usd__observed','bilateral_exports_usd__mirror_reference']:
  if f not in d:raise ValueError('Отсутствует: '+f)
 if c.year.min()>2000 or c.year.max()<2024:raise ValueError('Неполный временной диапазон')
 dq=tables['dyad_year'];bad=dq[(dq.source_id.astype(str)=='S05')&(dq.flow.astype(str)=='bilateral_trade_turnover_usd')].copy() if len(dq) else pd.DataFrame()
 return tables,{'countries':COUNTRIES,'country_rows':len(c),'dyad_rows':len(d),'base_year':2024,'quarantine_S05':len(bad)},bad

def transform(f,v):
 a=np.asarray(v,dtype=np.float64)
 return np.log1p(np.maximum(a,0)) if f in LOG_FEATS else a

class Prepared:
 """Immutable real historical tensors, source-coded trade edges, artificial state only in game."""
 def __init__(self,tables,seq_len=4):
  self.tables=tables;self.seq_len=seq_len;self.years=list(range(2000,2026));T=len(self.years)
  self.raw=np.full((T,N,len(FEATURES)),np.nan);self.obs=np.zeros_like(self.raw)
  self.glob=np.full((T,len(GLOB)),np.nan);self.gmask=np.zeros_like(self.glob)
  self.inst=np.zeros((T,N,len(INSTITUTIONS)),dtype=np.float32)
  self.exp=np.full((T,N,N),np.nan);self.mirror=np.full((T,N,N),np.nan)
  self.edge_source=np.zeros((T,N,N),dtype=np.int8) # 0 missing; 1 reporter; 2 mirror; 3 game-estimate only
  self.migrant=np.full((T,N,N),np.nan)
  for r in tables['game_country_state'].itertuples(index=False):
   y=int(r.year)-2000
   if not 0<=y<T:continue
   i=COUNTRIES.index(r.iso3)
   for j,k in enumerate(FEATURES):
    v=getattr(r,k);flag=getattr(r,k+'__observed',0)
    if pd.notna(v) and float(flag)==1:self.raw[y,i,j]=float(v);self.obs[y,i,j]=1
   for j,k in enumerate(INSTITUTIONS):self.inst[y,i,j]=float(getattr(r,k,0) or 0)
  for r in tables['game_global'].itertuples(index=False):
   y=int(r.year)-2000
   if not 0<=y<T:continue
   for j,k in enumerate(GLOB):
    v=getattr(r,k)
    if pd.notna(v) and float(getattr(r,k+'__observed',0))==1:self.glob[y,j]=float(v);self.gmask[y,j]=1
  for r in tables['game_dyads'].itertuples(index=False):
   y=int(r.year)-2000
   if not 0<=y<T:continue
   i=COUNTRIES.index(r.reporter_iso3);j=COUNTRIES.index(r.partner_iso3)
   v=r.bilateral_exports_usd;mirror=r.bilateral_exports_usd__mirror_reference
   if pd.notna(v) and float(r.bilateral_exports_usd__observed)==1 and v>=0:
    self.exp[y,i,j]=float(v);self.edge_source[y,i,j]=1
   elif pd.notna(mirror) and float(getattr(r,'bilateral_exports_usd__mirror_only',0))==1 and mirror>=0:
    self.mirror[y,i,j]=float(mirror);self.edge_source[y,i,j]=2
   mv=getattr(r,'migration_stock',np.nan)
   if pd.notna(mv) and float(getattr(r,'migration_stock__observed',0))==1:self.migrant[y,i,j]=float(mv)
  # Fit ONLY on historic TRAIN <=2014, without treating missing as real zero.
  self.fmean=[];self.fstd=[]
  for j,k in enumerate(FEATURES):
   v=transform(k,self.raw[:15,:,j]);v=v[np.isfinite(v)]
   self.fmean.append(float(v.mean()) if len(v) else 0.)
   self.fstd.append(max(float(v.std()) if len(v)>1 else 1.,0.01))
  self.fmean=np.array(self.fmean);self.fstd=np.array(self.fstd)
  self.gmean=np.nanmean(self.glob[:15],axis=0);self.gmean=np.nan_to_num(self.gmean,nan=0.)
  self.gstd=np.maximum(np.nan_to_num(np.nanstd(self.glob[:15],axis=0),nan=1.),.01)
  self.z=np.zeros_like(self.raw,dtype=np.float32)
  for j,k in enumerate(FEATURES):
   v=(transform(k,self.raw[:,:,j])-self.fmean[j])/self.fstd[j]
   self.z[:,:,j]=np.where(self.obs[:,:,j]>0,v,0)
  self.gz=np.where(self.gmask>0,(self.glob-self.gmean)/self.gstd,0).astype(np.float32)
  self.target_ix=np.array([FEATURES.index(f) for f in TARGETS]);self.graph=np.zeros((T,N,N),np.float32)
  self.confidence=np.zeros((T,N,N),np.float32)
  # Reporter observations + explicitly flagged partner mirrors are both published real data;
  # neither may become an invented direct-reporter historical observation.
  for y in range(T):
   for i in range(N):
    vals=np.where(self.edge_source[y,i]==1,self.exp[y,i],self.mirror[y,i]);known=np.isfinite(vals)
    if known.any():
     denom=vals[known].sum()
     if denom>0:self.graph[y,i,known]=(vals[known]/denom).astype(np.float32)
    self.confidence[y,i]=np.where(self.edge_source[y,i]==1,1.,np.where(self.edge_source[y,i]==2,.7,0.))
  # Gravity model trained ONLY on observed historic trade values <=2014; outputs later are game estimates, never observed.
  self.gravity=self._fit_gravity()
  self.game_graph,self.game_sources=self._build_game_graph(2024)
  self.dim_step=2*len(FEATURES)+2*len(GLOB)+len(INSTITUTIONS)+len(TARGETS)+2
  self.samples=[]
  for y in range(self.seq_len-1,T-1):
   for i in range(N):
    hist=np.stack([self.make_step(k,i) for k in range(y-self.seq_len+1,y+1)])
    # observed-to-observed normalized DELTA only; masks preserve missing history
    mask=(self.obs[y,i,self.target_ix]*self.obs[y+1,i,self.target_ix]).astype(np.float32)
    tgt=(self.z[y+1,i,self.target_ix]-self.z[y,i,self.target_ix])*mask
    self.samples.append((hist,tgt.astype(np.float32),mask,y+2000,i))
 def _fit_gravity(self):
  X=[];Y=[]
  idx=FEATURES.index('gdp_current_usd')
  for y in range(15):
   for i in range(N):
    for j in range(N):
     if i==j:continue
     v=self.exp[y,i,j] if self.edge_source[y,i,j]==1 else self.mirror[y,i,j]
     a=self.raw[y,i,idx];b=self.raw[y,j,idx]
     if pd.notna(v) and np.isfinite(a) and np.isfinite(b) and a>0 and b>0:
      X.append([1.,np.log1p(a),np.log1p(b),int(self.inst[y,i,0]*self.inst[y,j,0])]);Y.append(np.log1p(v))
  if len(X)<30:return [0.,.3,.3,0.]
  X=np.asarray(X);Y=np.asarray(Y);coef=np.linalg.solve(X.T@X+np.diag([1e-4,.3,.3,.3]),X.T@Y)
  return coef.tolist()
 def _build_game_graph(self,year):
  y=year-2000;values=np.zeros((N,N),float);codes=self.edge_source[y].copy();idx=FEATURES.index('gdp_current_usd')
  for i in range(N):
   for j in range(N):
    if i==j:continue
    v=self.exp[y,i,j] if codes[i,j]==1 else self.mirror[y,i,j] if codes[i,j]==2 else np.nan
    if not np.isfinite(v):
     # missing -> tagged MODEL_ESTIMATE, never official historical row
     a=self.raw[y,i,idx];b=self.raw[y,j,idx]
     if not np.isfinite(a):a=self.raw[y-1,i,idx]
     if not np.isfinite(b):b=self.raw[y-1,j,idx]
     a=max(1.,float(np.nan_to_num(a,nan=1e9)));b=max(1.,float(np.nan_to_num(b,nan=1e9)))
     beta=self.gravity;v=float(np.expm1(np.clip(beta[0]+beta[1]*np.log1p(a)+beta[2]*np.log1p(b)+beta[3]*self.inst[y,i,0]*self.inst[y,j,0],0,28)))
     codes[i,j]=3
    values[i,j]=max(0.,v)
  out=np.zeros_like(values,dtype=np.float32)
  for i in range(N):
   denom=values[i].sum()
   if denom>0:out[i]=(values[i]/denom).astype(np.float32)
  return out,codes
 def make_step(self,y,i,override=None):
  # state rows: most recent 4 yrs, graph neighbors observed on those years only
  if override is None:
   z=self.z[y];obs=self.obs[y];globalz=self.gz[y];globmask=self.gmask[y];inst=self.inst[y];adj=self.graph[y];conf=self.confidence[y]
  else:z,obs,globalz,globmask,inst,adj,conf=override
  nei=(adj[i,:,None]*z[:,self.target_ix]).sum(0)
  return np.r_[z[i],obs[i],globalz,globmask,inst[i],nei,float(adj[i].sum()),float(conf[i].mean())].astype(np.float32)
 def split(self,start,end):
  rows=[a for a in self.samples if start<=a[3]<=end]
  if not rows:raise ValueError('Нет временных рядов: '+str((start,end)))
  return (torch.from_numpy(np.stack([a[0] for a in rows])),torch.from_numpy(np.stack([a[1] for a in rows])),
          torch.from_numpy(np.stack([a[2] for a in rows])),np.array([[a[3],a[4]] for a in rows]))
 def meta(self):
  return {'countries':COUNTRIES,'features':FEATURES,'targets':TARGETS,'globals':GLOB,'institutions':INSTITUTIONS,
          'feature_mean':self.fmean.tolist(),'feature_std':self.fstd.tolist(),'global_mean':self.gmean.tolist(),
          'global_std':self.gstd.tolist(),'target_indices':self.target_ix.tolist(),'sequence_length':self.seq_len,
          'initial_2024':{'z':self.z[24].tolist(),'obs_mask':self.obs[24].tolist(),'institution':self.inst[24].tolist(),
              'global_z':self.gz[24].tolist(),'adj':self.game_graph.tolist(),'edge_source_code':self.game_sources.tolist()},
          'trade_source_code':{'0':'missing historical','1':'direct reporter official','2':'partner mirror official','3':'game-only model estimate'},
          'note':'Only original statistics enter supervised history; all game-only trade imputations have source_code=3.'}

class WorldNet(nn.Module):
 def __init__(self,dim,kind='GRU',hidden=48,seq_len=4):
  super().__init__();self.kind=kind;self.seq_len=seq_len;self.hidden=hidden
  if kind=='GRU':self.encoder=nn.GRU(dim,hidden,batch_first=True)
  elif kind=='LSTM':self.encoder=nn.LSTM(dim,hidden,batch_first=True)
  elif kind=='MLP':self.encoder=nn.Sequential(nn.Flatten(),nn.Linear(dim*seq_len,hidden),nn.Tanh(),nn.Linear(hidden,hidden),nn.SiLU())
  elif kind=='KAN':
   # compact spline-like RBF KAN-style nonlinear basis; explicitly NOT pykan library
   self.proj=nn.Linear(dim,hidden);self.centers=nn.Parameter(torch.linspace(-2,2,7),requires_grad=False)
   self.kan_weight=nn.Parameter(torch.randn(hidden,7,hidden)*.015)
   self.encoder=nn.Sequential(nn.LayerNorm(hidden),nn.SiLU())
  else:raise ValueError(kind)
  self.head=nn.Sequential(nn.Linear(hidden,hidden),nn.SiLU(),nn.Linear(hidden,len(TARGETS)))
 def forward(self,x):
  if self.kind in ('GRU','LSTM'):
   h,_=self.encoder(x);h=h[:,-1]
  elif self.kind=='KAN':
   h=self.proj(x[:,-1]);basis=torch.exp(-((h.unsqueeze(-1)-self.centers)**2)/.65)
   h=self.encoder(torch.einsum('bng,ngh->bh',basis,self.kan_weight))
  else:h=self.encoder(x)
  return self.head(h)

def masked_mse(pred,target,mask):return (((pred-target).square())*mask).sum()/mask.sum().clamp_min(1)

def train_world(prep,out,mode='FULL',seed=42,verbose=True):
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 tr=prep.split(2003,2014);va=prep.split(2015,2019);te=prep.split(2020,2024)
 X,Y,M,_=tr;V,W,VM,_=va;T,U,TM,_=te
 if M.sum()<80:raise RuntimeError('Недостаточно исходных наблюдаемых переходов')
 device='cuda' if torch.cuda.is_available() else 'cpu'
 models=[];runs=[];epochs=90 if mode=='FULL' else 3
 for kind in ['MLP','GRU','LSTM','KAN']:
  seed_all(seed+['MLP','GRU','LSTM','KAN'].index(kind)*17)
  net=WorldNet(X.shape[-1],kind=kind,seq_len=X.shape[1]).to(device)
  optim=torch.optim.AdamW(net.parameters(),lr=.0012,weight_decay=.025)
  best=float('inf');bad=0;best_weights=None
  for epoch in range(epochs):
   net.train();ids=torch.randperm(len(X))
   for idx in ids.split(48):
    xx=X[idx].to(device);yy=Y[idx].to(device);mm=M[idx].to(device)
    pred=net(xx);loss=masked_mse(pred,yy,mm)
    optim.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(net.parameters(),.8);optim.step()
   net.eval()
   with torch.no_grad():val=float(masked_mse(net(V.to(device)),W.to(device),VM.to(device)))
   if val<best-1e-5:best=val;bad=0;best_weights={k:v.detach().cpu().clone() for k,v in net.state_dict().items()}
   else:bad+=1
   if mode=='FULL' and bad>=16:break
  net.load_state_dict(best_weights);net.cpu().eval();models.append(net)
  runs.append({'kind':kind,'epochs':epoch+1,'val_mse_raw':best,'parameters':sum(p.numel() for p in net.parameters())})
  if verbose:print(f'World candidate {kind:4s}: val={best:.4f}, epochs={epoch+1}')
 # Pick model ONLY on validation and shrinkage towards persistence; 0 always available.
 val_base=float(masked_mse(torch.zeros_like(W),W,VM));test_base=float(masked_mse(torch.zeros_like(U),U,TM))
 selectors=[{'kind':'PERSISTENCE','alpha':0.,'val_mse':val_base,'model_idx':None}]
 with torch.no_grad():
  for i,net in enumerate(models):
   p=net(V)
   for alpha in [0.25,.5,.75,1.]:
    mse=float(masked_mse(p*alpha,W,VM))
    selectors.append({'kind':runs[i]['kind'],'alpha':alpha,'val_mse':mse,'model_idx':i})
 chosen=min(selectors,key=lambda x:x['val_mse']);winner=chosen['kind'];alpha=chosen['alpha']
 if winner=='PERSISTENCE':
  final=[];p=torch.zeros_like(U);ens_sd=0.
 else:
  # ensemble of 3 independently trained (small) networks of selected architecture; selection uses val ONLY
  final=[];ensemble_n=3 if mode=='FULL' else 1
  for k in range(ensemble_n):
   seed_all(seed+197+k)
   net=WorldNet(X.shape[-1],kind=winner,seq_len=X.shape[1]).to(device)
   opt=torch.optim.AdamW(net.parameters(),lr=.0012,weight_decay=.025)
   best=float('inf');best_w=None;bad=0
   for ep in range(epochs):
    net.train();ids=torch.randperm(len(X))
    for idx in ids.split(48):
     pred=net(X[idx].to(device));loss=masked_mse(pred,Y[idx].to(device),M[idx].to(device))
     opt.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(net.parameters(),.8);opt.step()
    net.eval()
    with torch.no_grad():vl=float(masked_mse(net(V.to(device))*alpha,W.to(device),VM.to(device)))
    if vl<best-1e-5:best=vl;bad=0;best_w={n:v.detach().cpu().clone() for n,v in net.state_dict().items()}
    else:bad+=1
    if mode=='FULL' and bad>=16:break
   net.load_state_dict(best_w);net.cpu().eval();final.append(net)
  with torch.no_grad():p=torch.stack([m(T) for m in final]).mean(0)*alpha
  ens_sd=float(torch.stack([m(T) for m in final]).std(0,unbiased=False).mean().detach())
  for k,net in enumerate(final):torch.save({'weights':net.state_dict(),'kind':winner,'dim':X.shape[-1],
               'seq_len':X.shape[1],'hidden':48,'alpha':alpha},out/f'world_{k}.pt')
 test=float(masked_mse(p,U,TM));per=[]
 with torch.no_grad():
  for j,f in enumerate(TARGETS):
   mask=TM[:,j]>0
   per.append({'target':f,'n':int(mask.sum()),'model_rmse_z':float(torch.sqrt(((p[mask,j]-U[mask,j])**2).mean())) if mask.any() else None,
               'persistence_rmse_z':float(torch.sqrt((U[mask,j]**2).mean())) if mask.any() else None})
 report={'candidates':runs,'selected_kind':winner,'shrink_alpha':alpha,'val_mse':chosen['val_mse'],
         'baseline_val_mse':val_base,'ensemble_test_mse':test,'baseline_test_mse':test_base,
         'better_than_persistence_on_test':bool(test<test_base),'per_target':per,'ensemble_disagreement':ens_sd,
         'splits':{'train_target_years':'2004-2015','validation_target_years':'2016-2020','test_target_years':'2021-2025'},
         'model_assessment':'validated_prediction' if test<test_base else 'scenario_only_not_predictive',
         'note':'Selection entirely on validation. If persistence selected, zero residual is a legitimate outcome; action impacts remain assumptions.'}
 write_json(report,out/'world_metrics.json');write_json(prep.meta(),out/'scalers_and_state.json')
 if verbose:print(f'WORLD SELECTED: {winner}, alpha={alpha:.2f}, heldout={test:.4f} vs persistence={test_base:.4f}')
 return final,report

def load_world(folder):
 folder=Path(folder);meta=json.loads((folder/'world_metrics.json').read_text())
 if meta['selected_kind']=='PERSISTENCE':return [],meta
 nets=[]
 for f in sorted(folder.glob('world_*.pt')):
  ck=torch.load(f,map_location='cpu',weights_only=False)
  net=WorldNet(ck['dim'],ck['kind'],seq_len=ck['seq_len'],hidden=ck['hidden']);net.load_state_dict(ck['weights']);net.eval();nets.append(net)
 if not nets:raise RuntimeError('Нет сохраненных весов выбранной World Model')
 return nets,meta

# Crisis event type determines channel of SHOCK, never fitted political treatment coefficient.
CRISIS_CHANNELS={
 'economic':(-.9,.18,-.55,-.25),'financial':(-.8,.35,-.35,-.5),
 'geopolitical':(-.55,.3,-.7,-.35),'technological':(.35,-.06,.25,.28),
 'demographic':(-.3,.12,-.18,-.1),'environmental':(-.45,.16,-.32,-.35),
 'pandemic':(-.8,.2,-.62,-.6),'elite':(-.25,.12,-.27,-.19)}

class CrisisEngine:
 def __init__(self,catalog,scenarios,seed=42,annual_rate=.34):
  self.catalog=[dict(x) for x in catalog];self.scenarios=[dict(x) for x in scenarios]
  self.byid={int(c['id']):c for c in catalog};self.rng=np.random.default_rng(seed)
  self.rate=annual_rate;self.active=[];self.regime=None
 def reset(self,seed=None):
  if seed is not None:self.rng=np.random.default_rng(seed)
  self.active=[];self.regime=None
 def events_at(self,year,mode='stochastic',scenario_id=None):
  started=[]
  if scenario_id:
   spec=next((s for s in self.scenarios if s['scenario_id']==scenario_id),None)
   if spec is None:raise ValueError('Unknown scenario: '+str(scenario_id))
   ix=(year-2025)
   for k,ev_id in enumerate(spec['crisis_ids']):
    if ix>=1 and (ix-1-4*k)%12==0:started.append(copy.deepcopy(self.byid[ev_id]))
  elif mode=='stochastic':
   for _ in range(min(2,int(self.rng.poisson(self.rate)))):
    started.append(copy.deepcopy(self.catalog[int(self.rng.integers(len(self.catalog)))]))
  for ev in started:
   ev['start_year']=year;ev['end_year']=min(2050,year+int(ev['duration'])-1);self.active.append(ev)
  current=[ev for ev in self.active if ev['end_year']>=year];self.active=current
  return started,current
 def inject_llm_event(self,payload,year):
  """Validate a structured LoRA proposal; NO arbitrary rule mutations or historical fabrication."""
  allowed=set(CRISIS_CHANNELS)
  typ=str(payload.get('event_type','')).lower()
  vec=np.asarray(payload.get('shocks',[]),float)
  countries=payload.get('affected_countries',[])
  duration=int(payload.get('duration_years',0))
  if typ not in allowed or vec.shape!=(4,) or not np.isfinite(vec).all() or np.any(np.abs(vec)>2):
   raise ValueError('LoRA crisis invalid type/shock bounds')
  if not 1<=duration<=4 or not isinstance(countries,list) or any((x not in COUNTRIES and x!='GLOBAL') for x in countries):
   raise ValueError('LoRA crisis invalid horizon/country list')
  # Institutional proposal is not auto-accepted: the game negotiation layer owns legal changes.
  ev={'id':int(payload.get('event_template_id',9000)),'name':'Сценарий Qwen (проверенный JSON)',
      'type':typ,'intensity':1.,'duration':duration,'affected':countries,
      'shock_override':vec.tolist(),'start_year':year,'end_year':min(2050,year+duration-1),
      'provenance':'llm_generated_synthetic_validated','requires_agent_approval':bool(payload.get('requires_agent_approval',True))}
  self.active.append(ev);return ev
 def effect(self,year,network,external=None,mode='stochastic',scenario_id=None):
  started,active=self.events_at(year,mode,scenario_id)
  country=np.zeros((N,4),float);channels=np.zeros(4,float);log=[]
  for ev in active:
   intensity=float(ev['intensity']);typ=ev['type'];sign=np.array(CRISIS_CHANNELS.get(typ,CRISIS_CHANNELS['economic']))
   # World shock amplitudes are assumption-bound, NOT empirical crisis intensity estimates.
   ch=np.asarray(ev.get('shock_override',sign*intensity*.65),float);channels+=ch
   targets=[COUNTRIES.index(c) for c in ev.get('affected',[]) if c in COUNTRIES]
   if not targets:targets=list(range(N)) # external-origin event reaches system globally
   propagated=np.zeros(N,float);propagated[targets]=1.
   propagated=np.clip(propagated+.45*network@propagated,0,1.3)
   country+=propagated[:,None]*ch[None,:]
   log.append({'event_id':int(ev['id']),'name':ev['name'],'year':year,'start_year':ev['start_year'],
               'type':typ,'intensity':intensity,'affected':ev['affected'],'assumed_effect':ch.round(4).tolist(),
               'event_provenance':ev.get('provenance','synthetic_template')})
  country=np.clip(country,-2.,2.);return country,log,started

class EurasiaEnv:
 """Independent game environment. Geography and membership are state, policies generate conditional—not causal—counterfactuals."""
 def __init__(self,prep,models,world_report,catalog,scenarios,seed=42,horizon=26,crisis_mode='stochastic',scenario_id=None,manual_events=None,rule_params=None):
  self.p=prep;self.models=models;self.world_report=world_report;self.seed=seed;self.rng=np.random.default_rng(seed)
  self.policy_rng=np.random.default_rng(seed+1187);self.crisis=CrisisEngine(catalog,scenarios,seed+313)
  self.horizon=horizon;self.crisis_mode=crisis_mode;self.scenario_id=scenario_id;self.manual_events=manual_events or {}
  self.rule_params={'crisis_annual_probability':.34,'institutional_cost_multiplier':1.,
   'project_cost_multiplier':1.,'risk_aversion_multiplier':1.}
  if rule_params:self.set_rule_params(rule_params,approved=True)
  self.reset()
 def set_rule_params(self,proposal,approved=False):
  # User/developer authorizes bounded parameter changes. Never execute generated code.
  if not approved:raise PermissionError('Human approval required for rule modification')
  bounds={'crisis_annual_probability':(.15,.60),'institutional_cost_multiplier':(.85,1.15),
   'project_cost_multiplier':(.85,1.15),'risk_aversion_multiplier':(.85,1.15)}
  for key,value in proposal.items():
   if key not in bounds:raise ValueError('Unknown mutable parameter: '+key)
   v=float(value);lo,hi=bounds[key]
   if not np.isfinite(v) or not lo<=v<=hi:raise ValueError('Parameter beyond safe bound: '+key)
   self.rule_params[key]=v
  if hasattr(self,'crisis'):self.crisis.rate=self.rule_params['crisis_annual_probability']
 def reset(self):
  self.year=2024;self.steps=0;self.z=self.p.z[24].copy();self.mask=self.p.obs[24].copy();self.instit=self.p.inst[24].copy()
  self.globalz=self.p.gz[24].copy();self.graph=self.p.game_graph.copy();self.source=self.p.game_sources.copy()
  self.energy=np.clip(.6+.005*np.nan_to_num(self.p.raw[24,:,FEATURES.index('investment_share_gdp')],nan=0),.35,1.)
  m=self.p.migrant[24].copy();self.migration_mask=np.isfinite(m).astype(np.float32)
  self.migration=np.maximum(0,np.nan_to_num(m,nan=0.))
  for i in range(N):
   denom=self.migration[i].sum()
   if denom>0:self.migration[i]/=denom
  # Absolute annual bilateral export amounts are separate from normalized exposure graph.
  # These are synthetic GAME quantities when the observed pair is not available.
  idx_gdp=FEATURES.index('gdp_current_usd');idx_exp=FEATURES.index('export_share_gdp')
  gdp=np.nan_to_num(self.p.raw[24,:,idx_gdp],nan=0.0)
  export_share=np.nan_to_num(self.p.raw[24,:,idx_exp],nan=0.0)
  totals=np.maximum(1e5,gdp*np.maximum(export_share,1.)/100.*.35)
  self.trade_usd=np.zeros((N,N),dtype=np.float64)
  for i in range(N):
   known=np.isin(self.source[i],[1,2]);known[i]=False
   published=np.where(self.source[i]==1,self.p.exp[24,i],self.p.mirror[24,i])
   self.trade_usd[i,known]=np.maximum(0.,published[known])
   missing=(self.source[i]==3);missing[i]=False
   remaining=max(0.,totals[i]-self.trade_usd[i].sum())
   # Gravity estimates are GAME-ONLY and do not replace real bilateral observations.
   proposal=self.graph[i,missing].astype(float)
   if missing.any() and proposal.sum()>0:self.trade_usd[i,missing]=remaining*proposal/proposal.sum()
  self.initial_trade_usd=float(self.trade_usd.sum())
  self.graph=self.trade_usd/np.maximum(self.trade_usd.sum(1,keepdims=True),1e-8)
  self.trade_observation_source=self.source.copy()
  self.project_pipeline=[];self.active_projects=[];self.agreement_register={};self.completed_projects=0
  self.last_new_projects=np.zeros(N,dtype=np.float32)
  self.last_active_agreements=np.zeros(N,dtype=np.float32)
  self.last_crisis_intensity=np.zeros(N,dtype=np.float32)
  self.project_audit=[];self.agreement_audit=[]
  self.crisis.rate=self.rule_params['crisis_annual_probability'];self.crisis.reset(self.seed+313);self.history=[];self.returns=np.zeros(N);self.action_history=[]
  # temporal history: observed 2021-2024; later append simulation states (synthetic flag)
  self.hist=[]
  for y in range(24-self.p.seq_len+1,25):
   self.hist.append((self.p.z[y].copy(),self.p.obs[y].copy(),self.p.gz[y].copy(),self.p.gmask[y].copy(),self.p.inst[y].copy(),
                     self.p.game_graph.copy() if y==24 else self.p.graph[y].copy(),np.where(self.p.edge_source[y]==1,1.,np.where(self.p.edge_source[y]==2,.7,0)).astype(np.float32)))
  return self.observe()
 def _histfeat(self):
  return np.stack([np.stack([self.p.make_step(0,i,override=h) for h in self.hist]) for i in range(N)])
 def observe(self):
  # [N,D] state with heterogeneous economic data, bilateral exposure and institutional posture
  pop=np.nan_to_num(self.p.raw[24,:,FEATURES.index('population_total')],nan=1e6)
  size=(np.log1p(np.maximum(pop,1))-12)/8
  extras=np.stack([self.graph.sum(1),self.graph.max(1),np.mean(self.source==3,axis=1),self.energy,
                   np.full(N,self.year/2050),size],axis=1)
  # Policy must observe actual negotiation outcomes and crisis exposure, not only yearly macro figures.
  extras2=np.stack([self.last_new_projects,self.last_active_agreements,self.last_crisis_intensity,
                   np.log1p(self.trade_usd.sum(1)/max(self.initial_trade_usd,1.))],axis=1)
  return np.concatenate([self.z,self.mask,self.instit,self.graph,self.graph.T,self.migration,self.migration_mask,extras,extras2],axis=1).astype(np.float32)
 def step(self,actions):
  ac=np.asarray(actions,int)
  if ac.shape!=(N,len(ACT_NAMES)):raise ValueError('Actions shape must be (8,6)')
  ac=np.clip(ac,0,2);self.year+=1;self.steps+=1
  trade=ac[:,0]-1;inv=ac[:,1]-1;coord=ac[:,2]-1;protect=ac[:,3]-1;focus=ac[:,4]-1;mobility=ac[:,5]-1
  before=self.graph.copy();prev=self.z.copy();previous_energy=self.energy.copy()
  # Formal proposal (level 2) requires at least negotiation/acceptance (level 1) by both parties.
  # Neutral action (level 1 for everyone) CANNOT create a project or agreement on its own.
  # Incumbent treaty expires after six years if not renewed. This is a game assumption.
  self.agreement_register={key:expiry for key,expiry in self.agreement_register.items() if expiry>=self.year}
  project=np.zeros((N,N),float);agreement=np.zeros((N,N),float)
  new_agreement_pairs=[];new_project_pairs=[]
  for i in range(N):
   for j in range(i+1,N):
    # Different national incentives: observable 2024 partner exposure, location in integration institution,
    # and capacity. Unknown shares remain explicitly simulated, not historic evidence.
    instituted=bool(self.instit[i,0]*self.instit[j,0]>0)
    compatible=bool((ac[i,4]>=1 and ac[j,4]>=1) or instituted)
    intends_treaty=bool(ac[i,2]>=1 and ac[j,2]>=1 and (ac[i,2]==2 or ac[j,2]==2))
    prev_treaty=(i,j) in self.agreement_register
    if intends_treaty and compatible:
     if not prev_treaty:new_agreement_pairs.append((i,j))
     agreement[i,j]=agreement[j,i]=1.
     self.agreement_register[(i,j)]=self.year+6
    has_treaty=((i,j) in self.agreement_register)
    intends_project=bool(ac[i,1]>=1 and ac[j,1]>=1 and (ac[i,1]==2 or ac[j,1]==2))
    negotiating=bool(ac[i,2]>=1 and ac[j,2]>=1)
    if intends_project and negotiating and (has_treaty or instituted):
     # Contract limited by poorer partner budget; no free unilateral projects.
     maximum=min(float(self.energy[i]),float(self.energy[j]))
     offer=(.18+.12*(ac[i,1]==2 and ac[j,1]==2))*maximum
     if offer>=.01:
      project[i,j]=project[j,i]=offer
      new_project_pairs.append((i,j))
  for i,j in new_agreement_pairs:
   self.agreement_audit.append({'year':self.year,'country_a':COUNTRIES[i],'country_b':COUNTRIES[j],
        'type':'new_bilateral_treaty','source':'synthetic_game_approved_by_both_agents'})
  mobility_agreements=np.zeros((N,N),float)
  for i in range(N):
   for j in range(i+1,N):
    legal=(self.instit[i,2]*self.instit[j,2]>0 or (coord[i]>0 and coord[j]>0))
    if mobility[i]>0 and mobility[j]>0 and legal:
     mobility_agreements[i,j]=mobility_agreements[j,i]=1.
  row_mobility=mobility_agreements.sum(1)/7.
  row_proj=project.sum(1);allocation=np.minimum(1.,self.energy/(row_proj+.01));project*=np.minimum(allocation[:,None],allocation[None,:]);row_proj=project.sum(1)
  # Explicit finite budget: pay upfront when project is accepted, earn delayed benefits.
  # One active/pending bilateral project per pair avoids artificial repeated investments.
  rejected_duplicate_pairs=[]
  for i,j in new_project_pairs:
   if any((q['i'],q['j'])==(i,j) for q in self.project_pipeline+self.active_projects):
    project[i,j]=project[j,i]=0.
    rejected_duplicate_pairs.append((i,j))
  # V4.7: only investments that passed duplicate/contract checks affect macro states and utility.
  # A rejected offer cannot create phantom growth, employment, or an investment share.
  row_proj=project.sum(1)
  for i in range(N):
   for j in range(i+1,N):
    amount=float(project[i,j])
    if amount<=0:continue
    self.project_pipeline.append({'i':i,'j':j,'maturity':self.year+2,
      'amount':amount,'expiry':self.year+8})
    self.project_audit.append({'year':self.year,'country_a':COUNTRIES[i],'country_b':COUNTRIES[j],
      'amount_index':amount,'maturity':self.year+2,'expiry':self.year+8,
      'source':'synthetic_contract_not_real_data'})
  mature=[q for q in self.project_pipeline if q['maturity']<=self.year]
  self.active_projects.extend(mature)
  self.project_pipeline=[q for q in self.project_pipeline if q['maturity']>self.year]
  self.active_projects=[q for q in self.active_projects if q['expiry']>=self.year]
  self.completed_projects+=len(mature)
  benefit=np.zeros(N,float)
  for q in self.active_projects:
   benefit[q['i']]+=.34*q['amount'];benefit[q['j']]+=.34*q['amount']
  # Resource constraints include BOTH negotiation administrative costs and actual joint investment.
  contract_cost=np.sum(project,axis=1)
  treaty_cost=np.zeros(N)
  for i,j in new_agreement_pairs:treaty_cost[[i,j]]+=.012
  self.energy=np.clip(self.energy-self.rule_params['project_cost_multiplier']*contract_cost
      -.014*(ac[:,1]==2)-self.rule_params['institutional_cost_multiplier']*treaty_cost
      -.03*np.maximum(0,protect),.025,1.5)
  # focus: trade-off between deepening and diversification, not free all-positive action.
  for i in range(N):
   weights=before[i].copy()
   self.graph[i]*=(1+.020*trade[i])
   if focus[i]==1:self.graph[i]*=(.985+.12*weights)
   if focus[i]==-1:self.graph[i]*=.97
   if coord[i]>0:
    for j in range(N):
     if agreement[i,j]:self.graph[i,j]*=1.02
   for j in range(N):
    if project[i,j]>0:self.graph[i,j]+=project[i,j]*.006
   np.fill_diagonal(self.graph,0)
   self.graph[i]=np.maximum(self.graph[i],0)
   # Preserve absolute exports: action changes total trade and allocation separately.
   relative=self.graph[i]/np.maximum(before[i],1e-8)
   relative=np.clip(relative,.65,1.35)
   self.trade_usd[i]*=relative
   self.trade_usd[i]=np.clip(self.trade_usd[i],0,1e15)
   denom=self.trade_usd[i].sum()
   self.graph[i]=self.trade_usd[i]/denom if denom>0 else before[i]
  concentration=(self.graph**2).sum(1);diversity=1.-concentration
  trade_level=np.log1p(self.trade_usd.sum()/max(self.initial_trade_usd,1.))
  injected=[]
  for proposed in self.manual_events.get(self.year,[]):
   injected.append(self.crisis.inject_llm_event(proposed,self.year))
  shocks,crisis_log,started=self.crisis.effect(self.year,self.graph,mode=self.crisis_mode,scenario_id=self.scenario_id)
  started=injected+started
  # Modelled crisis shock to absolute trade, linked to every country's local exposure.
  # Direct historical trade observations are immutable; this changes only future game states.
  crisis_trade_factor=np.clip(1+.035*shocks[:,2],.90,1.06)
  self.trade_usd*=crisis_trade_factor[:,None]
  self.graph=self.trade_usd/np.maximum(self.trade_usd.sum(1,keepdims=True),1e-8)
  self.last_crisis_intensity=np.clip(np.abs(shocks[:,0]),0,2).astype(np.float32)
  self.last_new_projects=(project>0).sum(1).astype(np.float32)/7.
  self.last_active_agreements=np.zeros(N,np.float32)
  for i,j in self.agreement_register:self.last_active_agreements[[i,j]]+=1/7.
  # World Model predicts residual in normalized TARGET space; all intervention effects are explicitly assumed.
  X=torch.from_numpy(self._histfeat()).float()
  alpha=float(self.world_report.get('shrink_alpha',0.))
  with torch.no_grad():
   preds=np.stack([m(X).numpy() for m in self.models]) if self.models else np.zeros((1,N,len(TARGETS)),np.float32)
  delta=alpha*preds.mean(0);uncertainty=float(preds.std(0).mean())
  new=prev.copy();country_growth=[]
  for j,key in enumerate(TARGETS):
   ix=self.p.target_ix[j];sd=self.p.fstd[ix]
   growth_effect=shocks[:,0]*(1-.19*protect)
   if key=='gdp_growth_pct':
    # Capital costs now, benefits after lag; trade policy and diversification have contingent gains.
    eff=growth_effect*2.4 + .35*trade*diversity + .26*row_proj+.48*benefit-.30*np.maximum(inv,0)-.16*np.maximum(protect,0)
   elif key=='cpi_inflation_pct':eff=shocks[:,1]*2.3+.16*np.maximum(inv,0)-.14*np.maximum(protect,0)
   elif key=='investment_share_gdp':eff=.6*inv + .2*row_proj+shocks[:,2]*1.1
   elif key=='export_share_gdp':eff=shocks[:,2]*2.0+.8*trade*(.2+diversity)+.2*focus
   elif key=='import_share_gdp':eff=shocks[:,2]*1.7+.6*trade
   elif key=='unemployment_pct':eff=shocks[:,3]*1.5-.2*row_proj+.2*np.maximum(inv,0)-.22*row_mobility+.08*np.maximum(mobility,0)
   elif key=='population_growth_pct':eff=shocks[:,3]*.10
   else:eff=shocks[:,3]*1.3+.18*row_mobility
   jdelta=np.clip(delta[:,j]+eff/max(sd,.01),-3.5,3.5)
   new[:,ix]=prev[:,ix]+jdelta+self.rng.normal(0,.015,N)
   val=np.clip(new[:,ix]*sd+self.p.fmean[ix],*BOUNDS[key]);new[:,ix]=(val-self.p.fmean[ix])/sd
  # GDP/population accounting propagated from the previous year, clearly simulated.
  for key,growthkey in [('gdp_current_usd','gdp_growth_pct'),('population_total','population_growth_pct')]:
   ix=FEATURES.index(key);gix=FEATURES.index(growthkey)
   old=np.expm1(np.clip(prev[:,ix]*self.p.fstd[ix]+self.p.fmean[ix],0,34))
   growth=new[:,gix]*self.p.fstd[gix]+self.p.fmean[gix]
   newraw=np.maximum(1e4,old*(1+growth/100))
   new[:,ix]=(np.log1p(newraw)-self.p.fmean[ix])/self.p.fstd[ix]
  ix=FEATURES.index('gdp_per_capita_usd');gi=FEATURES.index('gdp_current_usd');pi=FEATURES.index('population_total')
  gdp=np.expm1(new[:,gi]*self.p.fstd[gi]+self.p.fmean[gi]);pop=np.expm1(new[:,pi]*self.p.fstd[pi]+self.p.fmean[pi]);new[:,ix]=(np.log1p(gdp/np.maximum(pop,1))-self.p.fmean[ix])/self.p.fstd[ix]
  self.z=new;self.mask=np.ones_like(self.mask)
  self.globalz=np.clip(self.globalz+.02*self.rng.standard_normal(len(GLOB)),-4,4)
  conf=np.where(self.source==1,1.,np.where(self.source==2,.7,.2)).astype(np.float32)
  self.hist.append((self.z.copy(),self.mask.copy(),self.globalz.copy(),np.ones(len(GLOB),np.float32),
                     self.instit.copy(),self.graph.copy(),conf));self.hist=self.hist[-self.p.seq_len:]
  growth=self.z[:,FEATURES.index('gdp_growth_pct')]*self.p.fstd[FEATURES.index('gdp_growth_pct')]+self.p.fmean[FEATURES.index('gdp_growth_pct')]
  # non-monotone utility: resilience expensive in calm years, crucial in shocks; concentration makes deeper ties vulnerable
  exposure=np.maximum(np.abs(shocks[:,0]),0)*(0.3+concentration)
  # Pareto tradeoff: agreements have maintenance/negotiation costs, delayed project returns,
  # and risk from concentration. Reward does not simply pay for project count.
  cost_this_year=contract_cost+treaty_cost
  # V4.7: no direct prizes for project count, signed agreements, or mobility agreements.
  # Only the realized delayed project benefits (minus actual project spending) enter utility.
  # Project- and treaty-induced macro effects remain declared synthetic assumptions.
  reward_components={
   'growth':.13*np.clip(growth,-15,20),
   'diversification':.18*diversity,
   'realized_project_net_cash':.19*(benefit-contract_cost),
   'trade_income_proxy':.06*np.full(N,trade_level),
   'treaty_administration':-.11*treaty_cost,
   'protection_cost':-.11*np.maximum(protect,0),
   'negotiation_cost':-.016*self.rule_params['institutional_cost_multiplier']*np.maximum(coord,0),
   'crisis_exposure':-.18*self.rule_params['risk_aversion_multiplier']*exposure*(1-.36*np.maximum(protect,0)),
   'trade_concentration_cost':-.12*concentration*np.maximum(trade,0),
   'low_capital_penalty':-.06*(previous_energy<.15),
   'mobility_policy_cost':-.04*np.maximum(mobility,0),
  }
  rewards=sum(reward_components.values())
  rewards=np.clip(rewards,-5,5).astype(np.float32);self.returns+=rewards
  info={'year':self.year,'mean_growth_pct':float(growth.mean()),'growth_pct':growth.tolist(),
   'negotiation_offers':int(np.sum(coord>0)),'new_agreements':len(new_agreement_pairs),
   'new_projects':int(np.sum(np.triu(project>0,k=1))),
   'capital_budget_total':float(np.sum(self.energy)),
   'project_cash_out':float(np.sum(contract_cost)/2),
   'realized_project_volume_total':float(np.sum(project)/2),
   'rejected_duplicate_pairs':int(len(rejected_duplicate_pairs)),
   'project_reward_accounting':'realized_net_cash_only_no_activity_bonuses',
   'reward_components_mean':{k:float(np.mean(v)) for k,v in reward_components.items()},
   'project_benefit_current':float(np.sum(benefit)),
   'trade_concentration_mean':float(concentration.mean()),'network_strength':float(self.trade_usd.sum()/max(self.initial_trade_usd,1.)),'trade_usd_total':float(self.trade_usd.sum()),'projects':int((project>0).sum()/2),'agreements':int(agreement.sum()/2),'agreements_cumulative':len(self.agreement_register),'projects_matured':int(len(mature)),'projects_operating':int(len(self.active_projects)),'projects_cumulative_matured':int(self.completed_projects),
   'mobility_agreements':int(mobility_agreements.sum()/2),
   'mean_reward':float(rewards.mean()),'rewards':rewards.tolist(),'actions':ac.tolist(),
   'crises':crisis_log,'started_crises':started,'ensemble_disagreement':uncertainty,
   'synthetic':True,'policy_effects_assumed_not_identified':True,'rule_params':self.rule_params.copy()}
  self.action_history.append(ac.copy());self.history.append(info)
  return self.observe(),rewards,self.steps>=self.horizon,info

class Actor(nn.Module):
 def __init__(self,obs_dim,width=96):
  super().__init__();self.embed=nn.Embedding(N,12)
  self.body=nn.Sequential(nn.Linear(obs_dim+12,width),nn.Tanh(),nn.Linear(width,width),nn.Tanh())
  self.head=nn.Linear(width,len(ACT_NAMES)*3)
 def forward(self,obs):
  # obs [B,N,D], individual learned embeddings, not imposed country preferences
  ix=torch.arange(N,device=obs.device);e=self.embed(ix)[None].expand(obs.shape[0],-1,-1)
  z=self.body(torch.cat([obs,e],-1));return self.head(z).reshape(obs.shape[0],N,len(ACT_NAMES),3)
class Critic(nn.Module):
 def __init__(self,obs_dim,width=128):
  super().__init__();self.body=nn.Sequential(nn.Linear(N*obs_dim,width),nn.Tanh(),nn.Linear(width,width),nn.Tanh(),nn.Linear(width,N))
 def forward(self,x):return self.body(x.flatten(1))

def train_mappo(prep,models,world_report,catalog,scenarios,out,updates=90,env_count=8,rollout=16,ppo_epochs=3,seed=42,verbose=True,progress_callback=None,expert_pretrain_steps=0):
 out=Path(out);out.mkdir(parents=True,exist_ok=True);seed_all(seed)
 device='cuda' if torch.cuda.is_available() else 'cpu'
 envs=[EurasiaEnv(prep,models,world_report,catalog,scenarios,seed+31*i) for i in range(env_count)]
 obs=np.stack([e.observe() for e in envs]);actor=Actor(obs.shape[-1]).to(device);critic=Critic(obs.shape[-1]).to(device)
 opt=torch.optim.AdamW(list(actor.parameters())+list(critic.parameters()),lr=2e-4)
 # Curriculum/behavioral warm start: expert is a synthetic legal BARGAIN POLICY,
 # *not an observed national decision*. PPO subsequently trains entirely on-policy.
 if expert_pretrain_steps:
  expert_envs=[EurasiaEnv(prep,models,world_report,catalog,scenarios,seed+5501+k,horizon=26) for k in range(3)]
  supervised=torch.optim.AdamW(actor.parameters(),lr=.0007)
  for it_pre in range(expert_pretrain_steps):
   obslist=[];targets=[]
   for ee in expert_envs:
    if ee.steps>=ee.horizon:ee.reset()
    lead=(ee.year-2024)%N
    acts=np.ones((N,len(ACT_NAMES)),dtype=np.int64)
    acts[lead,1]=2;acts[lead,2]=2;acts[lead,4]=2
    # Other countries accept conditional offers, not forced investments.
    for partner in range(N):
     if ee.graph[lead,partner]>.05:acts[partner,1]=1;acts[partner,2]=1;acts[partner,4]=2
    obslist.append(ee.observe());targets.append(acts);ee.step(acts)
   xb=torch.as_tensor(np.stack(obslist),dtype=torch.float32,device=device)
   yb=torch.as_tensor(np.stack(targets),dtype=torch.long,device=device)
   probs=Categorical(logits=actor(xb));loss_pre=-probs.log_prob(yb).mean()
   supervised.zero_grad();loss_pre.backward();torch.nn.utils.clip_grad_norm_(actor.parameters(),.8);supervised.step()
   if progress_callback and ((it_pre+1)%5==0 or it_pre+1==expert_pretrain_steps):
    progress_callback(.12*(it_pre+1)/expert_pretrain_steps,
      f'Куррикулум договоров: {it_pre+1}/{expert_pretrain_steps} · imitation loss={float(loss_pre.detach()):.3f}')
  del supervised,expert_envs
 logs=[];best=-1e9;best_params=None;entropy_coeff=.027
 # Validation seeds/scenarios are disjoint from the final policy-promotion protocol.
 from eurasia_v46_guardrails import PolicyEarlyStopMonitor
 monitor=PolicyEarlyStopMonitor(out,seed,enabled=(updates>=30 and os.environ.get('EURASIA_V46_EARLY_STOP','1')=='1'),
       interval=int(os.environ.get('EURASIA_V46_MONITOR_INTERVAL','12')),
       patience=int(os.environ.get('EURASIA_V46_MONITOR_PATIENCE','4')),min_updates=36)
 kl_limit=float(os.environ.get('EURASIA_V46_KL_TARGET','0.035'));kl_early_stops=0;last_kl=0.;last_update=0
 for it in range(updates):
  record={k:[] for k in ['obs','acts','lp','val','rew','done']}
  diversity=[]
  for t in range(rollout):
   xo=torch.as_tensor(obs,dtype=torch.float32,device=device)
   with torch.no_grad():
    d=Categorical(logits=actor(xo));act=d.sample();lp=d.log_prob(act).sum(-1);val=critic(xo)
   acts=act.cpu().numpy();next_obs=[];rew=[];done=[]
   for k,env in enumerate(envs):
    new,r,finished,_=env.step(acts[k]);next_obs.append(env.reset() if finished else new)
    rew.append(r);done.append(float(finished))
   for k,v in [('obs',obs.copy()),('acts',acts.copy()),('lp',lp.cpu().numpy()),('val',val.cpu().numpy()),('rew',np.stack(rew)),('done',np.array(done,np.float32))]:record[k].append(v)
   obs=np.stack(next_obs)
  with torch.no_grad():bootstrap=critic(torch.tensor(obs,device=device,dtype=torch.float32)).cpu().numpy()
  vals=np.array(record['val']);rw=np.array(record['rew']);dn=np.array(record['done']);adv=np.zeros_like(rw);gae=np.zeros((env_count,N),np.float32)
  for t in reversed(range(rollout)):
   nval=bootstrap if t==rollout-1 else vals[t+1]
   active=(1-dn[t])[:,None];delta=rw[t]+.98*nval*active-vals[t]
   gae=delta+.98*.94*active*gae;adv[t]=gae
  returns=adv+vals
  flatten=lambda arr:torch.as_tensor(np.asarray(arr).reshape((-1,)+np.asarray(arr).shape[2:]),device=device)
  XO=flatten(record['obs']).float();AC=flatten(record['acts']).long();LP=flatten(record['lp']).float()
  AD=flatten(adv).float();RT=flatten(returns).float();AD=(AD-AD.mean())/(AD.std()+1e-6)
  for e in range(ppo_epochs):
   stop_ppo_epoch=False
   perm=torch.randperm(len(XO),device=device)
   for idx in perm.split(128):
    dist=Categorical(logits=actor(XO[idx]));logp=dist.log_prob(AC[idx]).sum(-1)
    ratio=torch.exp(torch.clamp(logp-LP[idx],-15,15))
    obj=-torch.minimum(ratio*AD[idx],torch.clamp(ratio,.8,1.2)*AD[idx]).mean()
    vloss=(critic(XO[idx])-RT[idx]).square().mean()
    ent=dist.entropy().sum(-1).mean();loss=obj+.45*vloss-entropy_coeff*ent
    if not bool(torch.isfinite(loss)):
     raise RuntimeError('PPO loss non-finite: model not promoted, frozen reserve remains available')
    opt.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(list(actor.parameters())+list(critic.parameters()),.8);opt.step()
    # PPO-specific KL guard against repeated destructive policy updates.
    with torch.no_grad():
     newlogp=Categorical(logits=actor(XO[idx])).log_prob(AC[idx]).sum(-1)
     lr=newlogp-LP[idx]
     last_kl=float(torch.mean(torch.exp(torch.clamp(lr,-15,15))-1-lr).cpu())
    if last_kl>1.5*kl_limit:
     stop_ppo_epoch=True;kl_early_stops+=1;break
   if stop_ppo_epoch:break
  metric=float(rw.mean());en=float(ent.detach());logs.append({'update':it+1,'mean_reward':metric,'policy_loss':float(obj.detach()),
      'value_loss':float(vloss.detach()),'entropy':en,'approx_kl':last_kl,'kl_early_stop_count':kl_early_stops,'action_diversity':float(np.unique(np.asarray(record['acts']).reshape(-1,len(ACT_NAMES)),axis=0).shape[0])})
  # choose model based on smoothed reward but PRESERVE diversity - not chase extreme single action reward
  recent=float(np.mean([v['mean_reward'] for v in logs[-5:]]));criterion=recent+.006*min(en,3)
  if criterion>best:
   best=criterion;best_params=({'actor':{k:v.detach().cpu().clone() for k,v in actor.state_dict().items()},
                               'critic':{k:v.detach().cpu().clone() for k,v in critic.state_dict().items()}})
  last_update=it+1
  if monitor.check(actor,critic,it+1,prep,models,world_report,catalog,scenarios,metric):
   if verbose:print('V4.6 PPO: early stop based on independent economic validation',it+1)
   break
  if progress_callback and (it==0 or (it+1)%2==0 or it+1==updates):
   progress_callback((.12+.88*(it+1)/updates) if expert_pretrain_steps else ((it+1)/updates),
        f'MAPPO {it+1}/{updates} · reward={metric:.3f} · entropy={en:.2f}')
  if verbose and (it==0 or (it+1)%10==0):print(f'MAPPO V4 {it+1}/{updates}: reward={metric:.3f}, entropy={en:.2f}, actions={logs[-1]["action_diversity"]:.0f}')
 guard_meta=monitor.finish(last_update)
 if monitor.enabled and monitor.best_params is not None:
  best_params=monitor.best_params
  guard_meta['checkpoint_rule']='Independent economic validation, not training reward'
 else:
  guard_meta['checkpoint_rule']='Training reward fallback: NOT externally validated'
 actor.load_state_dict(best_params['actor']);critic.load_state_dict(best_params['critic']);actor=actor.cpu().eval();critic=critic.cpu().eval()
 torch.save({'actor':actor.state_dict(),'critic':critic.state_dict(),'obs_dim':obs.shape[-1],
   'action_names':ACT_NAMES,'algo':'MAPPO_CTDE_V2_GUARDED','action_levels':3,'version':2},out/'mappo.pt')
 pd.DataFrame(logs).to_csv(out/'mappo_history.csv',index=False)
 return actor,critic,logs

def load_mappo(path):
 ck=torch.load(path,map_location='cpu',weights_only=False)
 if ck.get('version')!=2:raise ValueError('Требуется V2 MAPPO checkpoint')
 a=Actor(ck['obs_dim']);c=Critic(ck['obs_dim']);a.load_state_dict(ck['actor']);c.load_state_dict(ck['critic']);return a.eval(),c.eval()

def simulate(prep,models,world_report,actor,catalog,scenarios,seed=42,policy='MAPPO',horizon=26,scenario_id=None,crisis_mode='stochastic',sample_actions=True,manual_events=None,rule_params=None,progress_callback=None):
 env=EurasiaEnv(prep,models,world_report,catalog,scenarios,seed,horizon,crisis_mode,scenario_id,manual_events,rule_params)
 obs=env.observe()
 for t in range(horizon):
  if policy=='MAPPO':
   with torch.no_grad():d=Categorical(logits=actor(torch.tensor(obs[None],dtype=torch.float32))[0])
   if sample_actions:
    # dedicated stream guarantees reproducible policy trials for same seed
    logits=d.logits.numpy();pr=np.exp(logits-logits.max(-1,keepdims=True));pr=pr/pr.sum(-1,keepdims=True)
    acts=np.array([[env.policy_rng.choice(3,p=pr[i,k]) for k in range(len(ACT_NAMES))] for i in range(N)])
   else:acts=d.probs.argmax(-1).numpy()
  elif policy=='RANDOM':acts=env.policy_rng.integers(0,3,size=(N,len(ACT_NAMES)))
  elif policy=='NEUTRAL':acts=np.ones((N,len(ACT_NAMES)),dtype=int)
  elif policy=='AUTONOMY':acts=np.tile(np.array([0,0,0,2,0,0]),(N,1))
  elif policy=='COOPERATIVE':
   # Feasibility control only, not a claimed optimal solution. 2 = formal proposal, 1 = acceptance.
   acts=np.ones((N,len(ACT_NAMES)),dtype=int)
   acts[:,0]=2;acts[:,4]=2
   acts[:,1]=2;acts[:,2]=2
  elif policy=='BARGAIN':
   # Rotating voluntary proposals; distinct national investments, not enforced on all pairs.
   acts=np.ones((N,len(ACT_NAMES)),dtype=int)
   lead=(env.year-2024)%N
   acts[lead,1]=2;acts[lead,2]=2;acts[lead,4]=2
   for j in range(N):
    if env.graph[lead,j]>.05:acts[j,2]=1;acts[j,1]=1;acts[j,4]=2
  else:raise ValueError(policy)
  obs,rew,done,info=env.step(acts)
  if progress_callback:progress_callback((t+1)/horizon,env.year)
  if done:break
 return env.history,env.returns.tolist()

def eval_policies(prep,models,world_report,actor,catalog,scenarios,out,seed=42,n=8,progress_callback=None):
 rows=[];div=[]
 for k in range(n):
  si=seed+211*k
  for name in ['MAPPO','MAPPO_GREEDY','NEUTRAL','RANDOM','AUTONOMY']:
   history,returns=simulate(prep,models,world_report,actor,catalog,scenarios,seed=si,policy='MAPPO' if name=='MAPPO_GREEDY' else name,sample_actions=(name!='MAPPO_GREEDY'))
   actions=np.asarray([r['actions'] for r in history]);unique=[int(np.unique(actions[:,i,:],axis=0).shape[0]) for i in range(N)]
   rows.append({'seed':si,'policy':name,'total_reward':float(np.mean(returns)),
                'mean_final_growth_pct':history[-1]['mean_growth_pct'],
                'final_trade_concentration':history[-1]['trade_concentration_mean'],
                'total_crisis_exposures':sum(len(r['crises']) for r in history),
                'mean_unique_action_profiles':float(np.mean(unique))})
   if name in ('MAPPO','MAPPO_GREEDY'):
    div.append({'seed':si,'policy':name,'actions_unique_by_country':dict(zip(COUNTRIES,unique)),
        'across_countries_first_year_unique':int(np.unique(actions[0],axis=0).shape[0]),
        'across_countries_last_year_unique':int(np.unique(actions[-1],axis=0).shape[0]),
        'per_decision_entropy':{ACT_NAMES[j]:float(np.mean([-(v*np.log(np.maximum(v,1e-9))).sum() for v in [np.bincount(actions[:,i,j],minlength=3)/len(actions) for i in range(N)]])) for j in range(len(ACT_NAMES))}})
  if progress_callback:progress_callback((k+1)/n,f'Сравнение политик {k+1}/{n} наборов')
 pd.DataFrame(rows).to_csv(Path(out)/'policy_comparison.csv',index=False)
 write_json({'per_seed':div,'note':'Variation is diagnostic only; does not demonstrate real national preferences.'},Path(out)/'strategy_diversity.json')
 return pd.DataFrame(rows),div

def stress_scenarios(prep,models,world_report,actor,catalog,scenarios,out,seed=42,replicates=3,progress_callback=None,scenario_limit=None,horizon=26):
 if scenario_limit is not None:scenarios=scenarios[:int(scenario_limit)]
 traj=[];events=[];actions=[];aggregate=[]
 # fixed 20 designed scenarios, equal random seeds in MAPPO vs NEUTRAL; all 100 templates available in stochastic mode
 for sc_idx,sc in enumerate(scenarios):
  sid=sc['scenario_id']
  for k in range(replicates):
   s=seed+109*k
   for policy in ['MAPPO','MAPPO_GREEDY','NEUTRAL','BARGAIN']:
    his,rewards=simulate(prep,models,world_report,actor,catalog,scenarios,s,policy='MAPPO' if policy=='MAPPO_GREEDY' else policy,scenario_id=sid,crisis_mode='scenario',horizon=horizon,sample_actions=(policy!='MAPPO_GREEDY'))
    for rec in his:
     traj.append({'scenario_id':sid,'seed':s,'policy':policy,'year':rec['year'],
         'mean_growth_pct':rec['mean_growth_pct'],'trade_concentration':rec['trade_concentration_mean'],
         'mean_reward':rec['mean_reward'],'projects':rec['projects'],'agreements':rec['agreements'], 'projects_matured':rec.get('projects_matured',0),'projects_operating':rec.get('projects_operating',0),'agreements_cumulative':rec.get('agreements_cumulative',0),'trade_usd_total':rec.get('trade_usd_total',float('nan')),'network_strength':rec.get('network_strength',float('nan')),
          'new_agreements':rec.get('new_agreements',0),'new_projects':rec.get('new_projects',0),'capital_budget_total':rec.get('capital_budget_total',0),
          'project_cash_out':rec.get('project_cash_out',0),'project_benefit_current':rec.get('project_benefit_current',0),
         'crises_active':len(rec['crises']),'synthetic':True})
     for ev in rec['started_crises']:
      events.append({'scenario_id':sid,'seed':s,'policy':policy,'year':rec['year'],
          'event_id':ev['id'],'name':ev['name'],'type':ev['type'],'intensity':ev['intensity']})
     for i,c in enumerate(COUNTRIES):
      actions.append({'scenario_id':sid,'seed':s,'policy':policy,'year':rec['year'],'country':c,
           **{ACT_NAMES[j]:int(rec['actions'][i][j]) for j in range(len(ACT_NAMES))}})
    aggregate.append({'scenario_id':sid,'seed':s,'policy':policy,'reward':np.mean(rewards),
         'final_growth':his[-1]['mean_growth_pct'],'crisis_active_years':sum(bool(r['crises']) for r in his),
         'distinct_policy_vectors':len({tuple(r['actions'][i]) for r in his for i in range(N)})})
   if progress_callback:progress_callback((sc_idx*replicates+k+1)/(len(scenarios)*replicates),
       f'Сценарий {sid} · повтор {k+1}/{replicates}')
 for name,data in [('scenario_trajectories_2025_2050.csv',traj),('crisis_event_log.csv',events),
                   ('agent_actions.csv',actions),('stress_test_metrics.csv',aggregate)]:pd.DataFrame(data).to_csv(Path(out)/name,index=False)
 return pd.DataFrame(aggregate)
