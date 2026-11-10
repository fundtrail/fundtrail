# Inline the workspace menu module into the WorkspaceMenu card.
import os, sys
from pathlib import Path as _P
S = str(next(p for p in _P(__file__).resolve().parents if (p / 'system').is_dir() and (p / 'tools').is_dir()))  # frontend/design
root = S + '/system/components'
js = open(root + '/_src/workspace-menu.js').read()
t = open(S + '/tools/menus/card-template.html').read()
assert t.count('<!-- @menu-script -->') == 1
t = t.replace('<!-- @menu-script -->', '<!-- @menu-script -->\n<script>\n' + js + '\n</script>\n<!-- /menu-script -->')
open(root + '/WorkspaceMenu/preview.html', 'w').write(t); print('card built')
