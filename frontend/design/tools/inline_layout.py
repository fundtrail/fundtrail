# Inline the standard layout (option C: list and charge scroll separately, the thread docked at the bottom) into cards.
# Idempotent: run again to refresh. Demo gets chat-c.js, Charges gets charges-c.js; Evidence and GrantTerms get split-scroll.js
# (the same two scrolls, no thread dock). Pass card names to inline only those: inline_layout.py <root> Evidence GrantTerms.
import os, re, sys
from pathlib import Path as _P
S = str(next(p for p in _P(__file__).resolve().parents if (p / 'system').is_dir() and (p / 'tools').is_dir()))  # frontend/design
root = sys.argv[1]
SCRIPTS = {'Demo': 'chat-c.js', 'Charges': 'charges-c.js', 'Evidence': 'split-scroll.js', 'GrantTerms': 'split-scroll.js'}
for card in sys.argv[2:] or list(SCRIPTS):
    js = open(os.path.join(S, 'tools/chat', SCRIPTS[card])).read()
    block = '<!-- @layout-scripts -->\n<script>\n' + js + '\n</script>\n<!-- /layout-scripts -->'
    p = os.path.join(root, 'components', card, 'preview.html'); s = open(p).read()
    if '<!-- /layout-scripts -->' in s:
        s = re.sub(r'<!-- @layout-scripts -->.*?<!-- /layout-scripts -->', lambda m: block, s, flags=re.S)
    else:
        i = s.rfind('</body>'); assert i > 0, card; s = s[:i] + block + '\n' + s[i:]
    open(p, 'w').write(s); print('layout in', card, len(js))
