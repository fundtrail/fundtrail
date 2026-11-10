# Build the ProblemRecords and AcceptNote cards: inline components/_src/problems.js into each template.
import os
from pathlib import Path as _P
S = str(next(p for p in _P(__file__).resolve().parents if (p / 'system').is_dir() and (p / 'tools').is_dir()))  # frontend/design
root = S + '/system/components'
js = open(root + '/_src/problems.js').read()
for card in ['ProblemRecords', 'AcceptNote']:
    t = open(S + '/tools/problems/' + card + '.html').read()
    assert t.count('<!-- @problems-script -->') == 1, card
    t = t.replace('<!-- @problems-script -->', '<!-- @problems-script -->\n<script>\n' + js + '\n</script>\n<!-- /problems-script -->')
    os.makedirs(root + '/' + card, exist_ok=True)
    open(root + '/' + card + '/preview.html', 'w').write(t)
    print('built', card, len(t) // 1024, 'KB')
