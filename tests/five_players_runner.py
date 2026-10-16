#!/usr/bin/env python3
"""Five isolated Chrome browser profiles executing separate strategy game sessions."""
import concurrent.futures
import html
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

OUT = Path('/tmp/eurasia-qa-five')
OUT.mkdir(parents=True, exist_ok=True)
URL = 'http://127.0.0.1:8765/tests/five_players.html?player='

def run(player):
    profile = tempfile.mkdtemp(prefix=f'eurasia-player-{player}-')
    try:
        cmd = [
            'google-chrome', '--headless=new', '--no-sandbox', '--disable-gpu',
            '--disable-dev-shm-usage', '--no-first-run', '--disable-background-networking',
            '--no-default-browser-check', '--no-zygote',
            '--virtual-time-budget=60000', '--user-data-dir='+profile,
            '--window-size=1280,960', '--dump-dom', URL+str(player),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=110)
            source = result.stdout
            (OUT / f'player_{player}.html').write_text(source, encoding='utf-8')
            (OUT / f'player_{player}.stderr').write_text(result.stderr[-4000:], encoding='utf-8')
            match = re.search(r'<pre id="report">([\s\S]*?)</pre>', source)
            data = json.loads(html.unescape(match.group(1))) if match else {
                'player':player, 'errors':['Chrome did not finish browser test'],
                'process_returncode':result.returncode, 'source_tail':source[-800:],
            }
        except subprocess.TimeoutExpired:
            data={'player':player,'errors':['Chrome timed out after 110 seconds']}
        return data
    finally:
        shutil.rmtree(profile, ignore_errors=True)

with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    reports = sorted(executor.map(run, range(1, 6)), key=lambda x:x['player'])
(OUT / 'summary.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
for report in reports:
    ok = bool(report.get('checks')) and not report.get('errors')
    line = f"{'PASS' if ok else 'FAIL'} PLAYER {report['player']}: {len(report.get('checks',[]))} checks"
    print(line, flush=True)
    print('scenario:',json.dumps(report.get('configuration'),ensure_ascii=False),flush=True)
    print('results:',json.dumps(report.get('results'),ensure_ascii=False),flush=True)
    if report.get('changedInput'): print('changed_input:',report['changedInput'],flush=True)
    if report.get('invalidImportDebug'): print('invalid_import_debug:',json.dumps(report['invalidImportDebug'],ensure_ascii=False),flush=True)
    for error in report.get('errors', []): print('ERROR:',error,flush=True)
if not all(r.get('checks') and not r.get('errors') for r in reports):
    raise SystemExit('FAIL: at least one simulated player failed')
print('PASS QA: five isolated Chrome profiles, different scenarios and strategies')
