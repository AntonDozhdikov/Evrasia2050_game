from pathlib import Path
from zipfile import ZipFile
from hashlib import sha256
import json,csv,io
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'research/frozen/EURASIA_STAGE3_HANDOFF_V47.zip'
manifest=json.loads((ROOT/'research/results/data_manifest.json').read_text(encoding='utf8'))
assert source.is_file(), 'No frozen handoff archive'
assert sha256(source.read_bytes()).hexdigest()==manifest['source_sha256'], 'Frozen source checksum mismatch'
with ZipFile(source) as z:
    assert z.testzip() is None,'Corrupt source ZIP'
    for fname,expected in [('runtime/scenario_trajectories_2025_2050.csv',6240),('runtime/agent_actions.csv',49920)]:
        rows=list(csv.DictReader(io.StringIO(z.read(fname).decode('utf-8-sig'))))
        assert len(rows)==expected,(fname,len(rows),expected)
        local=ROOT/'research/results'/Path(fname).name
        assert sha256(local.read_bytes()).digest()==sha256(z.read(fname)).digest(),fname+' differs from archive'
    for path in ['runtime/metadata/scenarios_20.json','runtime/metadata/crises_future_100.json']:
        local=ROOT/'research/results'/Path(path).name
        assert local.read_bytes()==z.read(path)
print('PASS: frozen V4.7 source checksum, archive integrity, original CSV counts, data provenance')
