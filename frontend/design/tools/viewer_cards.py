# Rebuild the viewer cards on the shared frame (FTViewer.mount), keeping each card's dsCard line.
import os, re, sys
root = sys.argv[1]
cards = {'ViewerText': 'F1', 'ViewerEmail': 'F4', 'ViewerPdf': 'F5', 'ViewerPhoto': 'F6', 'ViewerSheet': 'F2'}
for card in sys.argv[2:]:
    fid = cards[card]; p = os.path.join(root, 'components', card, 'preview.html')
    first = open(p).read().splitlines()[0]
    h = int(re.search(r'height=(\d+)', first).group(1))
    body = f'''{first}
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{card} preview</title>
<style>body {{ margin: 0; background: var(--paper); }} .vs-host {{ height: {h}px; }}</style></head>
<body>
<section class="vs-host" id="vs" aria-label="Viewer"></section>
<!-- @viewer-scripts -->
<script>
(function () {{
  var h = {{}}; location.hash.replace(/^#/, '').split('&').forEach(function (kv) {{ var p = kv.split('='); if (p[0]) h[p[0]] = p[1] || ''; }});
  if (h.t) document.documentElement.setAttribute('data-theme', h.t);
  var f = FTViewer.files['{fid}'], k = h.fact ? parseInt(h.fact, 10) : null;
  var v = FTViewer.mount(document.getElementById('vs'), f, k);
  if (h.zoom && f.type !== 'text' && f.type !== 'email') {{ v.view.zoom = parseFloat(h.zoom); v.view.whole = false; v.draw(false); }}
  if (h.whole === '1') {{ v.view.whole = true; v.draw(false); }}
}})();
</script>
</body>
</html>
'''
    open(p, 'w').write(body); print('card', card, fid, h)
