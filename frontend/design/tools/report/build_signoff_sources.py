# Report pages 7 (open at sign-off, sign-off) and 8 and 9 (sources), generated from the data. Nothing is retyped.
# Inputs: _src/report-data.json, the F1 to F7 files in the viewer drafts, the golden fixture's evidence list.
import json, os, re, subprocess, sys, html, datetime as dt
from pathlib import Path as _P
S = str(next(p for p in _P(__file__).resolve().parents if (p / 'system').is_dir() and (p / 'tools').is_dir()))  # frontend/design
D = S + '/system/components/_src'
GOLDEN = S + '/system/components/_src/golden/evidence.json'
data = json.load(open(D + '/report-data.json'))
g = data['grant']; charges = sorted(data['charges'], key=lambda c: c['id'])
TOTAL_PAGES = 9
esc = lambda s: html.escape(str(s), quote=True)

# F1 to F7 as the app shows them (title, name, meta), read from the viewer drafts with node
js = r'''const vm=require('vm'),fs=require('fs');const sb={};sb.window=sb;sb.matchMedia=()=>({matches:false});sb.document={};vm.createContext(sb);
for (const f of ['viewer-text.js','viewer-pdf.js','viewer-photo.js']) vm.runInContext(fs.readFileSync(process.argv[1]+'/'+f,'utf8'),sb);
const out={};for (const [k,f] of Object.entries(sb.FTViewer.files)) out[f.name]={id:k,title:f.title,meta:f.meta};console.log(JSON.stringify(out));'''
F = json.loads(subprocess.check_output(['node', '-e', js, D]))
golden = {e['name']: e for e in json.load(open(GOLDEN))['evidence']}

def fdate(d): return d.strftime('%b ') + str(d.day) + d.strftime(', %Y')
CHANNEL = {'upload': 'Upload', 'gmail': 'Gmail', 'drive': 'Google Drive'}
def from_meta(meta):
    parts = [p.strip() for p in re.split(r'\s*·\s*', meta)]
    src = parts[0]
    channel = 'Upload' if src.startswith('Uploaded') else 'Gmail' if src.startswith('Gmail') else 'Google Drive' if src.startswith('Google Drive') else src
    sender = next((p[5:] for p in parts if p.startswith('from ')), '')
    return channel, sender, parts[-1]
def kind_of(name):
    if name.startswith('award_letter'): return 'Award letter'
    if name.startswith('extension_notice'): return 'Award amendment 01'
    if name.endswith('.eml'): return 'Email'
    if name.endswith('.jpg'): return 'Receipt photo'
    if name.startswith('psc_receipt_'): return 'Participant receipt'
    if name.startswith('receipt_'): return 'Receipt'
    if name.startswith('invoice'): return 'Invoice'
    return 'File'
def source_of(c):
    name = c['source']
    if name in F: return from_meta(F[name]['meta'])
    if name in golden:
        e = golden[name]; return CHANNEL[e['source']], e.get('sender', ''), fdate(dt.datetime.fromisoformat(e['arrived_at'].replace('Z', '+00:00')).date())
    # Synthetic files for the generated charges: invoices come by Gmail, receipts are uploaded, a few days after the purchase
    d = dt.date.fromisoformat(c['date']) + dt.timedelta(days=int(c['id'][2:]) % 7 + 2)
    return ('Gmail' if name.startswith('invoice') else 'Upload'), '', fdate(d)

def head(n):
    return ('<header class="ft-rpage__head"><span>Evidence report · <span class="ft-id">' + esc(g['award']) + '</span> · ' + esc(g['title']) + '</span>'
            '<span><span class="ft-rdraft">Draft</span> <span class="ft-rso-asof">As of ' + esc(g['asOf']) + '</span><span class="ft-rso-signedon">Signed off Apr 12, 2026</span></span></header>')
def foot(n):
    return '<footer class="ft-rpage__foot"><span>Prepared with FundTrail. All data in this demo is synthetic.</span><span>Page %d of %d</span></footer>' % (n, TOTAL_PAGES)
def page(n, body):
    return '<section class="ft-rpage" id="rp-%d" aria-label="Page %d of %d">' % (n, n, TOTAL_PAGES) + head(n) + '<div class="ft-rpage__body">' + body + '</div>' + foot(n) + '</section>\n'

# ---------- Page 7: open at sign-off, and sign-off ----------
NAMES = {'conflict': 'Possible conflict', 'human': 'Needs a human', 'missing': 'Missing evidence', 'complete': 'Evidence complete'}
CLOSE = {  # what would close each open charge, in the trail's own terms
 'L-0981': "The program officer's written approval, requested through Research.gov, or moving the charge off the grant.",
 'L-1010': "This grant's part of invoice SEQ-0311: an email or itemized invoice that gives the split, or the split entered by the accountant.",
 'L-1019': "The accountant's answer to the agent's question: is the field microscope camera for this project?",
}
order = {'conflict': 0, 'human': 1, 'missing': 2}
open_ = sorted([c for c in charges if c['bucket'] != 'complete'], key=lambda c: (order[c['bucket']], c['id']))
words = {1: 'One charge', 2: 'Two charges', 3: 'Three charges', 4: 'Four charges'}
items = ''.join(
  '<li class="ft-rso-item"><div class="ft-rso-item__top"><span class="ft-id">' + esc(c['id']) + '</span><span class="ft-rso-item__name">' + esc(c['desc']) + '</span>'
  '<span class="ft-rso-item__amt">' + esc(c['amount']) + '</span></div>'
  '<dl class="ft-rso-item__kv"><dt>Charged</dt><dd>' + esc(c['dateText']) + ' to ' + esc(c['line']) + '</dd>'
  '<dt>Bucket</dt><dd><span class="ft-rso-bucket"><span class="ft-tab-mark ft-tab-mark--' + c['bucket'] + '" aria-hidden="true"></span>' + NAMES[c['bucket']] + '</span></dd>'
  '<dt>Why</dt><dd>' + esc(c['reason']) + '</dd><dt>Would close it</dt><dd>' + esc(CLOSE[c['id']]) + '</dd></dl></li>' for c in open_)
p7 = ('<section class="ft-rso-section" aria-labelledby="rso-open"><h2 id="rso-open">Open at sign-off</h2>'
      '<p class="ft-rso-lede">' + words.get(len(open_), '%d charges' % len(open_)) + ' of ' + str(len(charges)) + ' aren’t Evidence complete. Each shows its bucket, the reason, and what would close it.</p>'
      '<ol class="ft-rso-list">' + items + '</ol></section>'
      '<section class="ft-rso-section" aria-labelledby="rso-sign"><h2 id="rso-sign">Sign-off</h2>'
      '<div class="ft-rso-sign">'
      '<div class="ft-rso-party"><h3>Prepared by</h3><p class="ft-rso-name">Taylor Example</p><p class="ft-rso-muted">Research Administrator, Department of Biology</p><p class="ft-rso-muted">taylor.example@university.example</p>'
      '<p class="ft-rso-state ft-rso-draftonly">Not signed off yet. This draft updates whenever a record changes.</p>'
      '<div class="ft-rso-signedonly"><p class="ft-rso-state">Signed off in FundTrail, Apr 12, 2026</p>'
      '<p class="ft-rso-notelabel">Note</p><p class="ft-rso-note">Three charges are still open. Each is listed above with what would close it.</p></div></div>'
      '<div class="ft-rso-party"><h3>Reviewed by</h3><p class="ft-rso-name">Quinn Example</p><p class="ft-rso-muted">Research Administration Manager</p>'
      '<p class="ft-rso-muted">Approves the Award Closeout Certification in BFS (Berkeley Financial System).</p>'
      '<div class="ft-rso-lines"><div class="ft-rso-line"><span class="ft-rso-rule"></span><span class="ft-rso-cap">Signature</span></div>'
      '<div class="ft-rso-line ft-rso-line--date"><span class="ft-rso-rule"></span><span class="ft-rso-cap">Date</span></div></div></div>'
      '</div></section>'
      '<p class="ft-rso-attach">Attach this report to the Award Closeout Certification in BFS, next to the CalAnswers ledger report, which shows only what was spent. FundTrail files nothing with the university or the National Science Foundation (NSF).</p>')
open(D + '/report-signoff.html', 'w').write(page(7, p7))

# ---------- Pages 8 and 9: sources ----------
terms = []
for name, scope in (('award_letter.txt', 'Grant terms for all %d charges' % len(charges)), ('extension_notice.txt', 'End date for all %d charges' % len(charges))):
    ch, sender, arrived = from_meta(F[name]['meta']); terms.append((scope, name, kind_of(name), ch, sender, arrived))
rows = []
for c in charges:
    ch, sender, arrived = source_of(c); rows.append((c['id'], c['source'], kind_of(c['source']), ch, sender, arrived))
    if c['id'] == 'L-0981': rows.append(('L-0981', 'registration_receipt.pdf', 'Receipt', 'Upload', '', 'Oct 4, 2025'))
def tr(r, scope=False):
    first = '<td>' + esc(r[0]) + '</td>' if scope else '<td><span class="ft-id">' + esc(r[0]) + '</span></td>'
    fr = esc(r[3]) + ('<span class="ft-rsrc-sender">' + esc(r[4]) + '</span>' if r[4] else '')
    return '<tr>' + first + '<td><span class="ft-rsrc-file">' + esc(r[1]) + '</span></td><td>' + esc(r[2]) + '</td><td>' + fr + '</td><td class="num">' + esc(r[5]) + '</td></tr>'
def table(label, first_col, body, caption_id):
    return ('<table class="ft-rtable ft-rsrc-table" aria-labelledby="' + caption_id + '"><colgroup><col class="ft-rsrc-c1"><col class="ft-rsrc-c2"><col class="ft-rsrc-c3"><col class="ft-rsrc-c4"><col class="ft-rsrc-c5"></colgroup>'
            '<thead><tr><th scope="col">' + first_col + '</th><th scope="col">File</th><th scope="col">Kind</th><th scope="col">From</th><th scope="col" class="num">Arrived</th></tr></thead><tbody>' + body + '</tbody></table>')
SPLIT = int(sys.argv[1]) if len(sys.argv) > 1 else 27
p8 = ('<h2>Sources</h2><p class="ft-rsrc-lede">Every file this report cites. The award documents come first, because every charge is checked against them. The rest follow in ledger line order, matching the table of charges, so a file can be found from its charge.</p>'
      '<h3 id="rsrc-terms">Award documents</h3>' + table('Award documents', 'Cited for', ''.join(tr(r, True) for r in terms), 'rsrc-terms') +
      '<h3 id="rsrc-ev">Evidence for each charge</h3>' + table('Evidence', 'Ledger line', ''.join(tr(r) for r in rows[:SPLIT]), 'rsrc-ev') +
      '<p class="ft-rsrc-cont">Continued on the next page.</p>')
p9 = ('<h3 id="rsrc-ev2">Evidence for each charge, continued</h3>' + table('Evidence', 'Ledger line', ''.join(tr(r) for r in rows[SPLIT:]), 'rsrc-ev2') +
      '<p class="ft-rsrc-note">' + str(len(terms) + len(rows)) + ' files in all. Each opens in FundTrail at the cited passage. Quotes in this report are checked against these files; boxes on photos are checked by a second look.</p>')
open(D + '/report-sources.html', 'w').write(page(8, p8) + page(9, p9))
print('page 7:', len(open_), 'open; sources:', len(terms), 'award docs +', len(rows), 'charge files, split', SPLIT, '/', len(rows) - SPLIT)
