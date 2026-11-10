# Build the GrantTerms card: inject the numbers from report-data.json, then inline the viewer.
import json, subprocess, sys
from pathlib import Path as _P
S = str(next(p for p in _P(__file__).resolve().parents if (p / 'system').is_dir() and (p / 'tools').is_dir()))  # frontend/design
R = S + '/system'
d = json.load(open(R + '/components/_src/report-data.json'))
cents = lambda s: int(round(float(s.replace('$', '').replace(',', '')) * 100))
budget = {}
for b in d['grant']['budget']:
    n = sum(1 for c in d['charges'] if c['line'] == b['line'])
    budget[b['line']] = {'budget': cents(b['budget']), 'charged': cents(b['charged']), 'n': n}
assert sum(v['charged'] for v in budget.values()) == sum(c['cents'] for c in d['charges'])
# The standing note example: Example Cloud Storage's charges, which all have an invoice, so none has the note's problem
storage = [c for c in d['charges'] if c['vendor'] == 'Example Cloud Storage' and c['line'] == 'Other Direct Costs']
assert all(c['bucket'] == 'complete' and c['source'].startswith('invoice_') for c in storage)
ids = [c['id'] for c in storage]
same = (', '.join(ids[:-1]) + ' and ' + ids[-1]) if len(ids) > 1 else (ids[0] if ids else '')
note = {'note': 'Example Cloud Storage bills the card on file each year and sends no invoice. The card statement in the department files is the record.',
        'problem': 'No bill on file', 'account': 'Other Direct Costs', 'vendor': 'Example Cloud Storage',
        'why': (same + ' have the same account and vendor, but each has an invoice on file, so none has this problem. A future charge that does is covered.') if ids else 'No charge on the grant matched it. A future charge with this problem, account and vendor is covered.'}
data = {'total': len(d['charges']), 'charged': d['grant']['charged'], 'counts': d['counts'], 'budget': budget, 'note': note}
t = open(S + '/tools/terms/template.html').read()
assert t.count('/*@DATA@*/null') == 1
t = t.replace('/*@DATA@*/null', json.dumps(data))
open(R + '/components/GrantTerms/preview.html', 'w').write(t)
for tool in ('inline_pr6.py', 'inline_viewer.py', 'inline_menu.py', 'inline_layout.py'):
    subprocess.run([sys.executable, S + '/tools/' + tool, R, 'GrantTerms'], check=True)
print('GrantTerms built', ids, {k: v['n'] for k, v in budget.items()})
