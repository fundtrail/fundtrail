import json, os, sys, html, re
root, out = sys.argv[1], sys.argv[2]
t = json.load(open(os.path.join(root, 'tokens.json')))
themes = [th['id'] for th in t['color']['themes']]
first = themes[0]
def val(tok, th):
    v = tok['value']
    if isinstance(v, str): return v if th == first else None
    return v.get(th)
def css_val(v):
    m = re.fullmatch(r'\{(.+)\}', v or '')
    return f'var(--{m.group(1)})' if m else v
blocks = []
for th in themes:
    sel = f':root, [data-theme="{th}"]' if th == first else f'[data-theme="{th}"]'
    lines = []
    for tok in t['color']['tokens'] + t.get('shadow', {}).get('tokens', []):
        v = val(tok, th)
        if v is None and th != first: continue
        if v is None: v = val(tok, themes[0])
        lines.append(f'  --{tok["name"]}: {css_val(v)};')
    blocks.append(sel + ' {\n' + '\n'.join(lines) + '\n}')
rest = []
for fam in ('spacing', 'radius', 'size', 'blur'):
    for tok in t.get(fam, {}).get('tokens', []): rest.append(f'  --{tok["name"]}: {tok["value"]};')
for k, v in t['type']['families'].items(): rest.append(f'  --font-{k}: {v};')
blocks.append(':root {\n' + '\n'.join(rest) + '\n}')
tokens_css = '\n'.join(blocks)
bundle = open(os.path.join(root, 'components/bundle.css')).read()
import glob
for _f in sorted(glob.glob(os.path.join(root, 'components/_src/*.css'))): bundle += '\n' + open(_f).read()
comps = sorted(d for d in os.listdir(os.path.join(root, 'components')) if os.path.isdir(os.path.join(root, 'components', d)))
comps = ['Cover'] + [c for c in comps if c != 'Cover']
if len(sys.argv) > 3: comps = sys.argv[3].split(',')
cells = []
for c in comps:
    src = open(os.path.join(root, 'components', c, 'preview.html')).read()
    m = re.search(r'height=(\d+)', src.splitlines()[0]); h = int(m.group(1)) if m else 120
    for th in themes:
        doc = src.replace('<html lang="en">', f'<html lang="en" data-theme="{th}">').replace('<html>', f'<html data-theme="{th}">')
        doc = doc.replace('<head>', f'<head><style>{bundle}</style><style>{tokens_css}</style>', 1)
        mw = re.search(r'width=(\d+)', src.splitlines()[0]); w = int(mw.group(1)) if mw else (960 if c == 'Cover' else 720)
        cells.append(f'<div class="cell"><div class="lab">{c} · {th}</div><iframe style="width:{w}px;height:{h+40}px" srcdoc="{html.escape(doc, quote=True)}"></iframe></div>')
if len(sys.argv) > 4:
    th = sys.argv[4]; c = comps[0]
    src = open(os.path.join(root, 'components', c, 'preview.html')).read()
    doc = src.replace('<html lang="en">', f'<html lang="en" data-theme="{th}">').replace('<head>', f'<head><style>{bundle}</style><style>{tokens_css}</style>', 1)
    open(out, 'w').write(doc); print('wrote single', out); sys.exit(0)
page = '<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0;padding:16px;background:#888;font:12px system-ui}.cell{margin:0 0 16px}.lab{color:#fff;margin:0 0 4px}iframe{border:0;display:block;background:#fff}</style></head><body>' + ''.join(cells) + '</body></html>'
open(out, 'w').write(page)
print('wrote', out, len(comps), 'components')
