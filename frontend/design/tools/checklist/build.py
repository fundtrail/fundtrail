# Build the EvidenceChecklist card: the template with components/_src/checklist.js inlined.
import os
from pathlib import Path as _P
S = str(next(p for p in _P(__file__).resolve().parents if (p / 'system').is_dir() and (p / 'tools').is_dir()))  # frontend/design
root = S + '/system/components'
t = open(S + '/tools/checklist/template.html').read()
js = open(root + '/_src/checklist.js').read()
assert t.count('<!-- @checklist-script -->') == 1
t = t.replace('<!-- @checklist-script -->', '<!-- @checklist-script -->\n<script>\n' + js + '\n</script>\n<!-- /checklist-script -->')
os.makedirs(root + '/EvidenceChecklist', exist_ok=True)
open(root + '/EvidenceChecklist/preview.html', 'w').write(t); print('EvidenceChecklist built', len(t))
