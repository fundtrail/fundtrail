# Assemble the EvidenceReport card from the page fragments in components/_src/report-*.html, in page order.
import os, re, sys, glob
root = sys.argv[1]
d = os.path.join(root, 'components/_src')
order = ['report-summary.html', 'report-table.html', 'report-sections.html', 'report-signoff.html', 'report-sources.html']
pages = ''.join(open(os.path.join(d, f)).read() for f in order if os.path.exists(os.path.join(d, f)))
card = os.path.join(root, 'components/EvidenceReport'); os.makedirs(card, exist_ok=True)
html = '''<!-- @dsCard group="Closeout" height=1100 width=900 subtitle="The evidence report: a PDF per grant, attached to the university's closeout step. Scroll for every page." -->
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>EvidenceReport preview</title>
<style>body { margin: 0; background: var(--paper-sunken); }</style></head>
<body>
<main class="ft-report" aria-label="Evidence report, SYN-2300117">
''' + pages + '''
</main>
<script>(function () { var h = {}; location.hash.replace(/^#/, '').split('&').forEach(function (kv) { var p = kv.split('='); if (p[0]) h[p[0]] = p[1] || ''; });
  if (h.t) document.documentElement.setAttribute('data-theme', h.t);
  if (h.signed === '1') document.documentElement.classList.add('is-signed');
  if (h.page) { var go = function () { var el = document.getElementById('rp-' + h.page); if (el) el.scrollIntoView(); }; go(); if (document.fonts && document.fonts.ready) document.fonts.ready.then(go); } })();</script>
</body>
</html>
'''
open(os.path.join(card, 'preview.html'), 'w').write(html)
print('built EvidenceReport with', len(re.findall(r'class="ft-rpage[" ]', pages)), 'pages')
