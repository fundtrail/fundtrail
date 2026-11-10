# Inline components/_src/thread.js into the ReviewThread card.
from pathlib import Path as _P
S = str(next(p for p in _P(__file__).resolve().parents if (p / 'system').is_dir() and (p / 'tools').is_dir()))  # frontend/design
root = S + '/system/components'
js = open(root + '/_src/thread.js').read()
t = open(S + '/tools/thread/template.html').read()
assert t.count('<!-- @thread-script -->') == 1
t = t.replace('<!-- @thread-script -->', '<!-- @thread-script -->\n<script>\n' + js + '\n</script>\n<!-- /thread-script -->')
open(root + '/ReviewThread/preview.html', 'w').write(t)
print('ReviewThread built', len(t))
