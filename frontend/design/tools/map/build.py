# Build the ScreenMap card: thumbnails as data URIs, one arrow drawing.
import base64, os, re
from pathlib import Path as _P
S = str(next(p for p in _P(__file__).resolve().parents if (p / 'system').is_dir() and (p / 'tools').is_dir()))  # frontend/design
t = open(S + '/tools/map/template.html').read()
arrow = '<svg viewBox="0 0 80 12" preserveAspectRatio="none" aria-hidden="true"><path d="M1 6H76" stroke="currentColor" stroke-width="1.5"/><path d="M71 1.5L77 6L71 10.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>'
t = t.replace('{{arrow}}', arrow)
def img(m):
    b = open(S + '/build/shots/map/' + m.group(1) + '.jpg', 'rb').read()
    return 'data:image/jpeg;base64,' + base64.b64encode(b).decode()
t = re.sub(r'\{\{(\w+)\}\}', img, t)
d = S + '/system/components/ScreenMap'; os.makedirs(d, exist_ok=True)
open(d + '/preview.html', 'w').write(t); print('ScreenMap', len(t) // 1024, 'KB')
