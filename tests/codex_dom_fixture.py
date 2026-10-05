#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Generate offline, real-browser checks when QtWebEngine is unavailable.

Run: uv run --offline tests/codex_dom_fixture.py --output ../_tmp/codex-dom --serve
Open the printed localhost URL in a browser; all eight checks must pass.
Only the route is injected. Extraction and verification scripts are unchanged.
"""
import argparse
import json
import runpy
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--serve', action='store_true')
parser.add_argument('--port', type=int, default=18763)
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
scripts = runpy.run_path(str(repo / 'src/aigauge/providers/_codex_page.py'))
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
label = lambda name, rest='': f'<div class="settings-row"><div><div><div>{name}</div></div></div>{rest}</div>'
tab = '<button aria-pressed="true">Overview</button>'
cases = [
  ('zh_weekly', tab + label('每週上限', '<span>5 天 10 小時後重設</span><span>剩餘 94%</span>')),
  ('partial_session', tab + '<section>' + label('5 hour usage limit') + label('Weekly limits', '<span>4 days until reset</span><span>94% remaining</span>') + '</section>'),
  ('partial_weekly', tab + '<section>' + label('5 hour usage limit', '<span>Resets in 4 hours</span><span>20% used</span>') + label('Weekly limits') + '</section>'),
  ('legacy_partial', '<section>' + label('5 hour usage limit') + label('Weekly usage limit', '<span>Resets in 4 days</span><span>94% remaining</span>') + '</section>'),
  ('historical_zero', tab + '<section><h2>Usage history</h2><div>Weekly limits</div><div>Period % of limit used</div><div>Sep 21-26</div><div>0% used</div></section>'),
  ('legacy_weekly', '<h2>Shared agentic usage limit</h2>' + label('Weekly usage limit', '<span>Resets in 4 days</span><span>94% remaining</span>') + '<div>Credits remaining</div>'),
  ('legacy_dual', label('5 hour usage limit','<span>Resets in 4 hours</span><span>20% used</span>') + label('Weekly usage limit', '<span>Resets in 5 days</span><span>30% used</span>')),
  ('delayed', '<button id="overview" aria-pressed="false" onclick="window.clickCount=(window.clickCount||0)+1">Overview</button><button aria-pressed="true">Analytics</button><section id="cards">Usage history</section>'),
]
runner = '''
const fakeLocation = {hostname:'chatgpt.com', pathname:'/settings/usage', href:'https://chatgpt.com/settings/usage?tab=overview'};
const extract = () => new Function('location', 'return ' + extractor)(fakeLocation);
const verify = () => new Function('location', 'return ' + verifier)(fakeLocation);
let result;
try {
  const first = extract();
  let passed = false;
  if (name === 'zh_weekly') passed = first.overview_ready === true && first.weekly.percent === 94 && first.weekly.kind === 'remaining' && first.weekly.reset_text === '5 天 10 小時' && verify() === true;
  if (name === 'partial_session' || name === 'partial_weekly' || name === 'historical_zero') passed = !!first.__retry_after_ms && first.weekly === null && verify() === false;
  if (name === 'legacy_partial') passed = first.session === null && verify() === false;
  if (name === 'legacy_weekly') passed = first.weekly.percent === 94 && first.session === null && verify() === true;
  if (name === 'legacy_dual') passed = first.session.percent === 20 && first.weekly.percent === 30 && verify() === true;
  if (name === 'delayed') {
    const second = extract();
    const oneClick = window.clickCount === 1;
    document.getElementById('overview').setAttribute('aria-pressed','true');
    document.getElementById('cards').innerHTML = '<div><div><div>Weekly limits</div></div><span>4 days until reset</span><span>94% remaining</span></div>';
    const third = extract();
    passed = first.__retry_reason === 'selected overview tab' && second.__retry_reason === 'waiting for Overview tab' && oneClick && window.clickCount === 1 && third.overview_ready === true && verify() === true;
    result = {name,passed,first,second,third,clicks:window.clickCount};
  }
  result ||= {name,passed,first};
} catch (error) {result = {name,passed:false,error:String(error)};}
const evidence = document.createElement('pre'); evidence.id='result'; evidence.textContent=JSON.stringify(result); document.body.appendChild(evidence);
parent.postMessage(result, window.location.origin);
'''
for name, body in cases:
    variables = 'const name=' + json.dumps(name) + ',extractor=' + json.dumps(scripts['EXTRACTOR_JS']) + ',verifier=' + json.dumps(scripts['VERIFY_JS']) + ';'
    (out / f'{name}.html').write_text('<!doctype html><meta charset="utf-8"><title>' + name + '</title>' + body + '<script>' + variables + runner + '</script>', encoding='utf-8')
index = '''<!doctype html><meta charset="utf-8"><title>AI Gauge offline DOM checks</title><h1>AI Gauge offline DOM checks</h1><p>Production extraction/verification scripts; local fixture route injected through a function parameter. No external requests.</p><pre id="results">Waiting...</pre><script>const results=[];window.addEventListener('message',e=>{if(e.origin!==location.origin||!e.data.name)return;results.push(e.data);document.getElementById('results').textContent=JSON.stringify(results,null,2);document.title=results.length+'/8 complete; '+results.filter(x=>x.passed).length+' passed';});</script>'''
index += ''.join(f'<iframe title="{name}" src="{name}.html" style="width:100%;height:190px"></iframe>' for name, _ in cases)
(out / 'index.html').write_text(index, encoding='utf-8')
print(out)
if args.serve:
    print(f'Offline fixture server: http://127.0.0.1:{args.port}/', flush=True)
    HTTPServer(('127.0.0.1', args.port), partial(SimpleHTTPRequestHandler, directory=str(out))).serve_forever()
