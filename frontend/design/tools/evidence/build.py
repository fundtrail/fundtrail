# Build the Evidence card's data from report-data.json, the F1 to F7 viewer files and the golden fixture. Nothing is retyped.
import json, os, re, subprocess, datetime as dt
from pathlib import Path as _P
S = str(next(p for p in _P(__file__).resolve().parents if (p / 'system').is_dir() and (p / 'tools').is_dir()))  # frontend/design
R = S + '/system'
D = R + '/components/_src'
GOLD = S + '/system/components/_src/golden'
data = json.load(open(D + '/report-data.json'))
charges = data['charges']

js = r'''const vm=require('vm'),fs=require('fs');const sb={};sb.window=sb;sb.matchMedia=()=>({matches:false});sb.document={};vm.createContext(sb);
for (const f of ['viewer-text.js','viewer-pdf.js','viewer-photo.js']) vm.runInContext(fs.readFileSync(process.argv[1]+'/'+f,'utf8'),sb);
const out={};for (const [k,f] of Object.entries(sb.FTViewer.files)) out[f.name]={id:k,type:f.type,title:f.title,meta:f.meta,links:f.links||[]};console.log(JSON.stringify(out));'''
F = json.loads(subprocess.check_output(['node', '-e', js, D]))
golden = {e['name']: e for e in json.load(open(GOLD + '/evidence.json'))['evidence']}

def fdate(d): return d.strftime('%b ') + str(d.day) + d.strftime(', %Y')
def parse(t): return dt.datetime.strptime(t, '%b %d, %Y').date()
CHANNEL = {'upload': 'Upload', 'gmail': 'Gmail', 'drive': 'Google Drive'}
def from_meta(meta):
    parts = [p.strip() for p in re.split(r'\s*·\s*', meta)]
    src = parts[0]
    ch = 'Upload' if src.startswith('Uploaded') else 'Gmail' if src.startswith('Gmail') else 'Google Drive' if src.startswith('Google Drive') else src
    sender = next((p[5:] for p in parts if p.startswith('from ')), '')
    return ch, sender, parts[-1]
def kind_of(name):
    if name.startswith('award_letter'): return 'Award letter', 'award'
    if name.startswith('extension_notice'): return 'Award amendment 01', 'award'
    if name.endswith('.eml'): return 'Email', 'emails'
    if name.endswith('.jpg'): return 'Receipt photo', 'photos'
    if name.startswith('psc_receipt_'): return 'Participant receipt', 'receipts'
    if name.startswith('receipt') or name.endswith('_receipt.pdf'): return 'Receipt', 'receipts'
    if name.startswith('invoice'): return 'Invoice', 'receipts'
    return 'File', 'receipts'
def source_of(c):
    name = c['source']
    if name in F: return from_meta(F[name]['meta'])
    if name in golden:
        e = golden[name]; return CHANNEL[e['source']], e.get('sender', ''), fdate(dt.datetime.fromisoformat(e['arrived_at'].replace('Z', '+00:00')).date())
    d = dt.date.fromisoformat(c['date']) + dt.timedelta(days=int(c['id'][2:]) % 7 + 2)
    return ('Gmail' if name.startswith('invoice') else 'Upload'), '', fdate(d)

files = []
def add(name, channel, sender, arrived, links, viewer=None, title=None, facts=None, note='', unlinked=False):
    k, group = kind_of(name)
    files.append(dict(name=name, kind=k, group=group, channel=channel, sender=sender, arrived=arrived, iso=parse(arrived).isoformat(),
                      links=links, viewer=viewer, title=title or k, facts=facts or [], note=note, unlinked=unlinked))

# The two award documents: terms for every charge
n = len(charges)
for name, note in (('award_letter.txt', 'Grant terms for all %d charges. Its end date was replaced by amendment 01, confirmed Apr 10, 2026.' % n),
                   ('extension_notice.txt', 'Grant terms: the end date for all %d charges. Confirmed by you, Apr 10, 2026.' % n)):
    ch, sender, arrived = from_meta(F[name]['meta'])
    add(name, ch, sender, arrived, [], viewer=F[name]['id'], title=F[name]['title'], note=note)

# One file per charge, from the report data; invoice_1001.txt is a real golden document, so it opens too (as F8)
gold_lines = open(GOLD + '/invoice_1001.txt').read().split('\n')
F8_FACTS = [('Invoice', 'INV-1001', 3, 'INVOICE INV-1001'), ('Vendor', 'Example Lab Supply Co.', 4, 'Example Lab Supply Co.'),
            ('Invoice date', 'Nov 12, 2025', 5, 'November 12, 2025'), ('Item', 'Sediment core liners, 50 count', 9, 'Sediment core liners, 50 count'),
            ('Total', '$1,240.00', 11, '$1,240.00')]
for lab, val, line, text in F8_FACTS: assert text in gold_lines[line - 1], (line, text)
seen = set()
for c in sorted(charges, key=lambda c: c['id']):
    name = c['source']; assert name not in seen, name; seen.add(name)
    ch, sender, arrived = source_of(c)
    if name in F:
        add(name, ch, sender, arrived, F[name]['links'], viewer=F[name]['id'], title=F[name]['title'])
    elif name == 'invoice_1001.txt':
        add(name, ch, sender, arrived, [dict(id=c['id'], name=c['desc'], amount=c['amount'] + ' of ' + c['amount'])], viewer='F8', title='Invoice INV-1001')
    else:
        k = kind_of(name)[0]
        facts = [dict(label='Vendor', value=c['vendor']), dict(label='Date', value=c['dateText']), dict(label='Item', value=c['desc']), dict(label='Total', value=c['amount'])]
        add(name, ch, sender, arrived, [dict(id=c['id'], name=c['desc'], amount=c['amount'] + ' of ' + c['amount'])], title=k + ', ' + c['vendor'], facts=facts)
    if c['id'] == 'L-0981':  # the registration receipt the report cites next to the approval email
        add('registration_receipt.pdf', 'Upload', '', 'Oct 4, 2025', [dict(id=c['id'], name=c['desc'], amount=c['amount'] + ' of ' + c['amount'])],
            title='Receipt, Example Ocean Sciences Meeting', facts=[dict(label='Vendor', value='Example Ocean Sciences Meeting'), dict(label='Item', value='Meeting registration'), dict(label='Total', value=c['amount'])])
# A bill no charge uses (decision 0010): a record that goes on the problem list 60 days after it arrived, if still unlinked
arr = dt.date(2026, 3, 30); listed = arr + dt.timedelta(days=60)
add('invoice_2050.pdf', 'Gmail', '', fdate(arr), [], title='Invoice 2050, Example Field Station', unlinked=True,
    facts=[dict(label='Vendor', value='Example Field Station'), dict(label='Total', value='$5,000.00')],
    note='$5,000.00 that no charge on this grant uses. Paid another way, or charged to another grant?')
files[-1]['listing'] = "Goes on the problem list %s, if it's still not linked." % fdate(listed)
files[-1]['problem'] = 'Bill not charged: $5,000.00, linked to no charge'
assert fdate(listed) == 'May 29, 2026', fdate(listed)
files.sort(key=lambda f: (f['iso'], f['name']), reverse=True)
assert len(files) == 55, len(files)

out = dict(files=files, F8=dict(id='F8', type='text', name='invoice_1001.txt', title='Invoice INV-1001', meta='Uploaded by you · Nov 12, 2025',
           links=[dict(id='L-1001', name='Sediment core liners', amount='$1,240.00 of $1,240.00')], note='', lines=gold_lines,
           facts=[dict(label=a, value=b, line=l, text=t) for a, b, l, t in F8_FACTS], active=4),
           counts=dict(all=len(files), unlinked=sum(f['unlinked'] for f in files), award=sum(f['group'] == 'award' for f in files),
                       receipts=sum(f['group'] == 'receipts' for f in files), emails=sum(f['group'] == 'emails' for f in files), photos=sum(f['group'] == 'photos' for f in files)))
t = open(S + '/tools/evidence/template.html').read()
t = t.replace('/*@EVIDENCE_DATA@*/', 'window.FTEvidence = ' + json.dumps(out).replace('</', '<\\/') + ';')
os.makedirs(R + '/components/Evidence', exist_ok=True)
open(R + '/components/Evidence/preview.html', 'w').write(t)
subprocess.check_call(['python3', S + '/tools/inline_viewer.py', R, 'Evidence'], stdout=subprocess.DEVNULL)
for tool in ('inline_pr6.py', 'inline_menu.py', 'inline_layout.py'): subprocess.check_call(['python3', S + '/tools/' + tool, R, 'Evidence'], stdout=subprocess.DEVNULL)
print('Evidence built:', out['counts'])
