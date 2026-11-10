# Inline the PR 6 modules (thread, checklist, problems) into cards that carry <!-- @pr6-scripts -->. Run again to refresh.
import os, re, sys
root = sys.argv[1]
d = os.path.join(root, 'components/_src')
js = '\n'.join(open(os.path.join(d, f)).read() for f in ['thread.js', 'checklist.js', 'problems.js'] if os.path.exists(os.path.join(d, f)))
block = '<!-- @pr6-scripts -->\n<script>\n' + js + '\n</script>\n<!-- /pr6-scripts -->'
for card in sys.argv[2:]:
    p = os.path.join(root, 'components', card, 'preview.html'); s = open(p).read()
    if '<!-- /pr6-scripts -->' in s: s = re.sub(r'<!-- @pr6-scripts -->.*?<!-- /pr6-scripts -->', lambda m: block, s, flags=re.S)
    else: assert s.count('<!-- @pr6-scripts -->') == 1, card + ': add <!-- @pr6-scripts --> before your own script'; s = s.replace('<!-- @pr6-scripts -->', block)
    open(p, 'w').write(s); print('pr6 modules in', card, len(js))
