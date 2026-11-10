# A standalone page with every screen: an overview grid, then each screen full size, joined by its own buttons.
import base64, json, re, subprocess, sys
from pathlib import Path as _P
S = str(next(p for p in _P(__file__).resolve().parents if (p / 'system').is_dir() and (p / 'tools').is_dir()))  # frontend/design
sys.argv = ['x']; exec(open(S + '/tools/walk/build.py').read().split("meta = [")[0])  # reuses SCREENS, NAV and data
meta = [dict(id=x[0], label=x[1], hash=x[3], stage=x[4], hint=x[5]) for x in SCREENS]
thumbs = {'signin': 'signin', 'home': 'home', 'add': 'ag2', 'grant': 'answer', 'charges': 'charges', 'evidence': 'evidence', 'terms': 'terms', 'closeout': 'closeout', 'report': 'report', 'map': 'map'}
import os
BLANK = 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=='  # a clear pixel when a thumbnail hasn't been shot
def thumb(name):
    f = S + '/build/shots/map/%s.jpg' % name
    return 'data:image/jpeg;base64,' + base64.b64encode(open(f, 'rb').read()).decode() if os.path.exists(f) else BLANK
for m in meta: m['thumb'] = thumb(thumbs[m['id']])
w = open(S + '/build/shots/walk/w.html').read()
tokens = re.findall(r'<style>(.*?)</style>', w, re.S)[1]   # the token block the harness wrote
page = open(S + '/tools/walk/standalone.html').read()
page = page.replace('/*CLOCK*/', open(S + '/tools/walk/shell-clock.js').read()).replace('/*TOKENS*/', tokens).replace('/*META*/', json.dumps(meta)).replace('/*DOCS*/', json.dumps(data).replace('</', '<\\/'))
os.makedirs(S + '/build', exist_ok=True); open(S + '/build/screens.html', 'w').write(page); print(len(page) // 1024, 'KB')
