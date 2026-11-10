# Inline the workspace and account menus (components/_src/workspace-menu.js) into app-shell cards, before </body>.
import os, re, sys
root = sys.argv[1]
js = open(os.path.join(root, 'components/_src/workspace-menu.js')).read()
HOME = '''
(function () {
  /* On the workspace home, switching workspaces redraws the page; the redraw replaces the Account button, so attach again */
  function nav(kind, value) {
    if (kind !== 'workspace' || !window.FTWorkspaceRender) return;
    window.FTWorkspaceRender(value === 'bio' ? 'biology' : 'demo');
    window.FTWorkspaceMenu.attach({ current: value, onNavigate: nav });
    return false;
  }
  window.FTWorkspaceMenu.attach({ current: /state=empty/.test(location.hash) ? 'bio' : 'demo', onNavigate: nav });
})();
'''
for card in sys.argv[2:]:
    call = HOME if card == 'Workspace' else '\nwindow.FTWorkspaceMenu && window.FTWorkspaceMenu.attach();\n'
    block = '<!-- @menu-scripts -->\n<script>\n' + js + call + '</script>\n<!-- /menu-scripts -->'
    p = os.path.join(root, 'components', card, 'preview.html'); s = open(p).read()
    if '<!-- /menu-scripts -->' in s: s = re.sub(r'<!-- @menu-scripts -->.*?<!-- /menu-scripts -->', lambda m: block, s, flags=re.S)
    else:
        i = s.rfind('</body>'); assert i > 0, card; s = s[:i] + block + '\n' + s[i:]
    open(p, 'w').write(s); print('menu in', card)
