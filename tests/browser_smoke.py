"""Optional end-to-end test in a normal local Chrome/Chromium runtime.

Install: pip install playwright && python -m playwright install chromium
Run: python tests/browser_smoke.py
"""
from pathlib import Path
from contextlib import contextmanager
from playwright.sync_api import sync_playwright
import subprocess, time, socket, sys

ROOT = Path(__file__).resolve().parents[1]
PORT = 18765

@contextmanager
def serve():
    process = subprocess.Popen(
        [sys.executable, '-m', 'http.server', str(PORT), '--bind', '127.0.0.1'],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', PORT), .2):
                    break
            except OSError:
                time.sleep(.1)
        yield f'http://127.0.0.1:{PORT}/'
    finally:
        process.terminate()
        try: process.wait(timeout=4)
        except subprocess.TimeoutExpired: process.kill()

with serve() as url, sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    errors = []
    page = browser.new_page(viewport={'width': 1440, 'height': 960}, accept_downloads=True)
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(url, wait_until='load', timeout=45000)
    assert page.locator('#scenario option').count() == 20
    assert page.locator('#policy option').count() == 4
    assert page.locator('#seed option').count() == 3
    assert page.locator('#actions .agent-row').count() == 8
    assert page.locator('#chart svg').count() == 1
    page.select_option('#scenario', 'S20')
    page.select_option('#policy', 'BARGAIN')
    page.select_option('#seed', '381')
    page.locator('#year').fill('2050')
    assert page.locator('#selectedYear').inner_text() == '2050'
    page.locator('[data-code="KAZ"]').click()
    assert 'Казахстан' in page.locator('#countryDetail').inner_text()
    with page.expect_download() as out:
        page.locator('#exportCsv').click()
    assert out.value.suggested_filename.endswith('.csv')
    mobile = browser.new_page(viewport={'width': 390, 'height': 844})
    mobile.on('pageerror', lambda e: errors.append(str(e)))
    mobile.goto(url, wait_until='load', timeout=45000)
    assert mobile.locator('#actions .agent-row').count() == 8
    assert not errors, errors
    browser.close()
print('PASS browser: scenarios, strategies, years, countries, export, desktop and mobile')
