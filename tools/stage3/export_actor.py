#!/usr/bin/env python3
"""Export the frozen MAPPO V4.7 PyTorch actor without importing or executing PyTorch.

The frozen archive is immutable. Only known torch storage/tensor pickle constructors
are allowed; no arbitrary Python globals are deserialized.
"""
from __future__ import annotations
import collections
import csv
import hashlib
import io
import itertools
import json
import math
from pathlib import Path
import pickle
import struct
import zipfile

ROOT=Path(__file__).resolve().parents[2]
ARCHIVE=ROOT/'research/frozen/EURASIA_STAGE3_HANDOFF_V47.zip'
OUTPUT=ROOT/'assets/policy_v47.js'
COUNTRIES=['RUS','BLR','KAZ','KGZ','UZB','TJK','TKM','ARM']

class FloatStorage: pass
class DoubleStorage: pass
class LongStorage: pass
class HalfStorage: pass
class BFloat16Storage: pass

class Storage:
    def __init__(self,key,dtype,raw):self.key,self.dtype,self.raw=key,dtype,raw

class Tensor:
    def __init__(self,storage,offset,shape,stride):
        self.shape=list(shape)
        self.stride=list(stride)
        spec={FloatStorage:('f',4),DoubleStorage:('d',8),LongStorage:('q',8),HalfStorage:('e',2)}
        if storage.dtype not in spec:raise ValueError('Unsupported storage data type '+str(storage.dtype))
        code,width=spec[storage.dtype]
        if math.prod(shape)>300000:raise ValueError('Unexpectedly large checkpoint tensor')
        self.values=[]
        for index in itertools.product(*(range(n) for n in shape)):
            ix=int(offset)+sum(i*k for i,k in zip(index,stride))
            self.values.append(float(struct.unpack_from('<'+code,storage.raw,width*ix)[0]))
        if any(not math.isfinite(v) for v in self.values):raise ValueError('Non-finite checkpoint weight')
    def json(self):return {'shape':self.shape,'values':self.values}

def tensor_v2(storage,offset,shape,stride,*_):
    if not isinstance(storage,Storage):raise TypeError('Non-storage tensor')
    return Tensor(storage,offset,shape,stride)

class SafeTorch(pickle.Unpickler):
    def __init__(self,buf,zipfile_handle,prefix):
        super().__init__(buf)
        self.z=zipfile_handle
        self.prefix=prefix
        self.storages={}
    def find_class(self,module,name):
        types={
          ('collections','OrderedDict'):collections.OrderedDict,
          ('torch._utils','_rebuild_tensor_v2'):tensor_v2,
          ('torch._utils','_rebuild_tensor'):tensor_v2,
          ('torch','FloatStorage'):FloatStorage,
          ('torch','DoubleStorage'):DoubleStorage,
          ('torch','LongStorage'):LongStorage,
          ('torch','HalfStorage'):HalfStorage,
          ('torch','BFloat16Storage'):BFloat16Storage
        }
        key=(module,name)
        if key not in types:raise pickle.UnpicklingError('Disallowed pickle constructor '+str(key))
        return types[key]
    def persistent_load(self,pid):
        if not isinstance(pid,tuple) or len(pid)!=5 or pid[0]!='storage':
            raise pickle.UnpicklingError('Disallowed persistent pickle ID')
        _,dtype,key,location,size=pid
        if location!='cpu':raise ValueError('Unexpected non-CPU storage')
        if key not in self.storages:
            raw=self.z.read(self.prefix+'data/'+key)
            if len(raw)>10_000_000:raise ValueError('Oversized storage')
            self.storages[key]=Storage(key,dtype,raw)
        return self.storages[key]

def main():
    with zipfile.ZipFile(ARCHIVE) as z:
        raw=z.read('runtime/marl/mappo.pt')
        meta=json.loads(z.read('runtime/world/scalers_and_state.json'))
        with zipfile.ZipFile(io.BytesIO(raw)) as pt:
            name=next(x for x in pt.namelist() if x.endswith('/data.pkl'))
            checkpoint=SafeTorch(io.BytesIO(pt.read(name)),pt,name[:-len('data.pkl')]).load()
        assert checkpoint['version']==44, f"Expected V4.4 gated actor inside V4.7, got {checkpoint['version']}"
        actor=checkpoint['actor'];gates=checkpoint['evolution_gates']
        if not isinstance(gates,Tensor):raise ValueError('Missing gated MAPPO tensor')
        expected={
          'embed.weight':[8,12],
          'body.0.weight':[96,checkpoint['obs_dim']+12],
          'body.0.bias':[96],
          'body.2.weight':[96,96],
          'body.2.bias':[96],
          'head.weight':[18,96],
          'head.bias':[18]
        }
        for key,shape in expected.items():
            if key not in actor or actor[key].shape!=shape:
                raise ValueError('Unexpected actor parameter '+key+' '+str(getattr(actor.get(key),'shape',None)))
        if gates.shape!=[4,8,6,3]:raise ValueError('Invalid V4.4 conditional gates shape')
        populations={c:1000000.0 for c in COUNTRIES}
        with z.open('runtime/game_input_tables/game_country_state.csv') as fh:
            rows=csv.DictReader(io.TextIOWrapper(fh,encoding='utf-8-sig'))
            for row in rows:
                if row.get('year')=='2024' and row.get('iso3') in populations:
                    if str(row.get('population_total__observed','0')) in ('1','1.0'):
                        try:populations[row['iso3']]=float(row['population_total'])
                        except (ValueError,TypeError):pass
        migration=[[0.0]*8 for _ in range(8)]
        migrationmask=[[0.0]*8 for _ in range(8)]
        with z.open('runtime/game_input_tables/game_dyads.csv') as fh:
            rows=csv.DictReader(io.TextIOWrapper(fh,encoding='utf-8-sig'))
            for row in rows:
                if row.get('year')!='2024':continue
                a=row.get('reporter_iso3');b=row.get('partner_iso3')
                if a not in COUNTRIES or b not in COUNTRIES or a==b:continue
                if str(row.get('migration_stock__observed','0')) in ('1','1.0'):
                    try:mv=float(row['migration_stock'])
                    except (ValueError,TypeError):continue
                    if math.isfinite(mv):
                        i=COUNTRIES.index(a);j=COUNTRIES.index(b)
                        migration[i][j]=max(0,mv);migrationmask[i][j]=1
        for i in range(8):
            sm=sum(migration[i])
            if sm>0:migration[i]=[v/sm for v in migration[i]]
        source=meta['initial_2024']['edge_source_code']
        obs_dim=len(meta['features'])*2+len(meta['institutions'])+8*4+10
        if checkpoint['obs_dim']!=obs_dim:raise ValueError(f"Observation dimension mismatch {checkpoint['obs_dim']} != {obs_dim}")
        output={
         'schema':'EURASIA_FROZEN_MAPPO_V47_PORT_1',
         'provenance':{'archive_sha256':hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),
                       'checkpoint_sha256':hashlib.sha256(raw).hexdigest(),
                       'checkpoint_version':checkpoint['version'],
                       'model':'V4.7 original MAPPO Actor + V4.4 bounded state gates',
                       'source':'research/frozen/EURASIA_STAGE3_HANDOFF_V47.zip:runtime/marl/mappo.pt',
                       'training':'none; exact frozen checkpoint export',
                       'policy_effects':'assumed synthetic-game interventions'},
         'obs_dim':obs_dim,
         'feature_names':meta['features'],
         'target_indices':meta['target_indices'],
         'feature_mean':meta['feature_mean'],
         'feature_std':meta['feature_std'],
         'initial_z':meta['initial_2024']['z'],
         'initial_mask':meta['initial_2024']['obs_mask'],
         'initial_instit':meta['initial_2024']['institution'],
         'source':source,
         'population':[populations[c] for c in COUNTRIES],
         'migration':migration,
         'migration_mask':migrationmask,
         'actor':{name:actor[name].json() for name in expected},
         'gates':gates.json()
        }
        txt=json.dumps(output,ensure_ascii=False,allow_nan=False,separators=(',',':'))
        OUTPUT.write_text("(function(root,factory){const v=factory();if(typeof module==='object'&&module.exports)module.exports=v;else root.EURASIA_ACTOR_V47=v;})(typeof self!=='undefined'?self:this,function(){return "+txt+";});\n",encoding='utf-8')
        print('STAGE3_EXPORTED',OUTPUT,OUTPUT.stat().st_size,'obs_dim',obs_dim)
        print('STAGE3_SHA',output['provenance']['checkpoint_sha256'])
        print('STAGE3_COUNTRIES',len(populations),'migration_nonzero',sum(bool(a) for row in migration for a in row))
if __name__=='__main__':main()
