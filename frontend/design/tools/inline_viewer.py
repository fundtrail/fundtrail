# Inline the viewer scripts (components/_src/viewer-*.js) into cards that carry the marker.
import os, re, sys
root = sys.argv[1]
d = os.path.join(root, 'components/_src')
order = ['viewer-frame.js', 'viewer-text.js', 'viewer-pdf.js', 'viewer-photo.js', 'viewer-report.js']
js = '\n'.join(open(os.path.join(d, f)).read() for f in order if os.path.exists(os.path.join(d, f)))
block = '<!-- @viewer-scripts -->\n<script>\n' + js + '\n</script>\n<!-- /viewer-scripts -->'
for card in sys.argv[2:]:
    p = os.path.join(root, 'components', card, 'preview.html'); s = open(p).read()
    if '<!-- /viewer-scripts -->' in s:
        s = re.sub(r'<!-- @viewer-scripts -->.*?<!-- /viewer-scripts -->', lambda m: block, s, flags=re.S)
    else:
        assert s.count('<!-- @viewer-scripts -->') == 1, card
        s = s.replace('<!-- @viewer-scripts -->', block)
    open(p, 'w').write(s); print('inlined', card, len(js))
