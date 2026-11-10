# Report pages 4 to 6: six charge sections, two per page. Amounts and budget figures come from report-data.json.
import json, html, sys
root = sys.argv[1]
d = json.load(open(root + '/components/_src/report-data.json'))
C = {c['id']: c for c in d['charges']}
B = {b['line']: b for b in d['grant']['budget']}
E = html.escape
BN = {'complete': 'Evidence complete', 'conflict': 'Possible conflict', 'human': 'Needs a human', 'missing': 'Missing evidence'}
RES = {'pass': 'Passes', 'fail': 'Fails', 'human': 'Needs a human', 'missing': 'Not on file'}

def room(line):
    b = B[line]; return '%s of %s charged to %s.' % (b['charged'], b['budget'], line)

def section(cid, checks, evidence, history, decisions=()):
    c = C[cid]
    rows = ''.join('<tr><td class="ft-rx__check">%s</td><td><span class="ft-rx__res ft-rx__res--%s">%s</span></td><td>%s</td><td class="ft-rx__who">%s</td></tr>'
                   % (E(name), kind, E(label or RES[kind]), why, who) for name, kind, label, why, who in checks)
    ev = ''.join('<li><span>%s</span><span class="ft-rx__src">%s</span></li>' % (q, E(src)) for q, src in evidence)
    hi = ''.join('<li><span class="ft-rx__date">%s</span><span>%s</span></li>' % (E(dt), t) for dt, t in history)
    de = ''.join('<li><span>%s</span><span class="ft-rx__src">%s</span></li>' % (E(t), E(n)) for t, n in decisions)
    de = f'<div class="ft-rx__block"><span class="ft-rx__label">Decisions</span><ul class="ft-rx__ev">{de}</ul></div>' if de else ''
    return f'''<article class="ft-rx" aria-labelledby="rx-{cid}">
  <header class="ft-rx__head">
    <div><span class="ft-rx__meta"><span class="ft-id">{cid}</span> <span class="ft-sep">&middot;</span> {E(c['dateText'])} <span class="ft-sep">&middot;</span> {E(c['line'])} <span class="ft-sep">&middot;</span> {E(c['vendor'])}</span><h2 id="rx-{cid}">{E(c['desc'])}</h2></div>
    <div class="ft-rx__right"><span class="ft-rx__amt">{E(c['amount'])}</span><span class="ft-badge ft-badge--{c['bucket']}">{BN[c['bucket']]}</span></div>
  </header>
  <table class="ft-rtable ft-rx__checks"><thead><tr><th>Check</th><th>Result</th><th>Why</th><th>By</th></tr></thead><tbody>{rows}</tbody></table>
  <div class="ft-rx__block"><span class="ft-rx__label">Evidence</span><ul class="ft-rx__ev">{ev}</ul></div>
  {de}
  <div class="ft-rx__block"><span class="ft-rx__label">Status history</span><ol class="ft-rx__hist">{hi}</ol></div>
</article>'''

def q(text): return '<span class="ft-quote">&ldquo;%s&rdquo;</span>' % E(text)
def approx(what): return '<span class="ft-rx__approx">Box checked by a second look: %s</span>' % E(what)
def arrow(a, b): return '%s <span class="ft-arrow" aria-label="changed to">&rarr;</span> %s' % (BN[a], BN[b])
def to(b): return 'Bucket set to %s' % BN[b]

S = {}
S['L-1002'] = section('L-1002', [
  ('Period of performance', 'pass', None, 'Feb 20, 2026, before the new end date, Jan 31, 2027.', 'Code'),
  ('Evidence checklist', 'pass', '1 of 1 filled', 'A bill that adds up (account default): invoice SEQ-0207, $2,180.00 of $2,180.00.', 'Code'),
  ('Budget room', 'pass', None, room('Other Direct Costs') + ' Line assigned by the agent.', 'Code'),
  ('Necessary, reasonable and for this project', 'pass', 'Supports', 'Sequencing of Example Bay sediment samples, the project’s own work.', 'Agent'),
], [
  (q('changed from January 31, 2026 to January 31, 2027'), 'extension_notice.txt, line 8 · Google Drive, Apr 10, 2026'),
  (q('Total Due: $2,180.00'), 'sequencing_invoice.eml, line 16 · Gmail, Feb 21, 2026'),
  (q('February 1, 2023 through January 31, 2026') + ' <span class="ft-rx__note">Replaced by amendment 01</span>', 'award_letter.txt, line 15 · upload, Jan 12, 2023'),
], [
  ('Feb 24, 2026', 'Ledger line L-1002 arrived. ' + to('conflict') + ': work done after the end date then in force.'),
  ('Apr 10, 2026', 'New end date confirmed by the accountant. ' + arrow('conflict', 'complete') + '.'),
], [
  ('Confirmed amendment 01, Apr 10, 2026, by the accountant.', 'Replaced the award letter’s end date, Jan 31, 2026'),
])
S['L-0981'] = section('L-0981', [
  ('Period of performance', 'pass', None, 'Registered Oct 3, 2025, inside the period.', 'Code'),
  ('Evidence checklist', 'missing', '1 of 2 filled', 'Bill (account default): registration receipt, $650.00 of $650.00. Program officer’s written approval (added by code from the approval rule): not on file.', 'Code'),
  ('Approver’s role and channel', 'fail', None, 'Approved by the principal investigator by email. Participant support costs need the program officer’s written approval, through Research.gov.', 'Code'),
  ('Budget room', 'pass', None, room('Participant Support Costs'), 'Code'),
], [
  (q('Approved, go ahead and register.'), 'approval_email.eml, line 9 · Gmail, Oct 6, 2025'),
  (q('without prior written approval from the Program Officer, requested through Research.gov'), 'award_letter.txt, line 19 · upload, Jan 12, 2023'),
], [
  ('Oct 6, 2025', 'Approval email arrived. ' + arrow('missing', 'conflict') + '.'),
])
S['L-1010'] = section('L-1010', [
  ('Period of performance', 'pass', None, 'Run done Jan 9, 2026, inside the period.', 'Code'),
  ('Evidence checklist', 'human', 'Needs the split', 'A bill that adds up (account default): invoice SEQ-0311 is $10,000.00 for a run shared with another grant. Nothing on file gives this grant’s part: an email or itemized invoice, or a split entered by the accountant.', 'Code'),
  ('Budget room', 'pass', None, room('Other Direct Costs'), 'Code'),
], [
  (q('Run shared by awards SYN-2300117 and SYN-2300245.'), 'invoice_SEQ-0311.pdf, page 1 · Gmail, Jan 12, 2026'),
  (q('$10,000.00') + ' <span class="ft-rx__note">Total due</span>', 'invoice_SEQ-0311.pdf, page 1 · Gmail, Jan 12, 2026'),
], [
  ('Jan 13, 2026', 'Ledger line L-1010 arrived. ' + to('human') + '.'),
])
S['L-1019'] = section('L-1019', [
  ('Period of performance', 'pass', None, 'Bought Jan 21, 2026, inside the period.', 'Code'),
  ('Evidence checklist', 'pass', '1 of 1 filled', 'A bill that adds up (account default): receipt photo, Example Optics Supply, $1,325.00 of $1,325.00.', 'Code'),
  ('Budget room', 'pass', None, room('Materials and Supplies') + ' Line assigned by the agent.', 'Code'),
  ('For this project', 'human', 'Unsure', 'The receipt names a field camera, but nothing on file ties it to the sediment survey.', 'Agent'),
], [
  (approx('Total, $1,325.00'), 'field_camera_receipt.jpg · upload, Jan 22, 2026'),
  (approx('Field camera, microscope mount'), 'field_camera_receipt.jpg · upload, Jan 22, 2026'),
], [
  ('Jan 23, 2026', 'Ledger line L-1019 arrived. ' + to('human') + ': the agent is unsure.'),
])
S['L-1015'] = section('L-1015', [
  ('Period of performance', 'pass', None, 'Rented Jan 14, 2026, inside the period.', 'Code'),
  ('Evidence checklist', 'pass', '1 of 1 filled', 'A bill that adds up (account default): receipt photo, Example Marina, $1,480.00 of $1,480.00, arrived Apr 12, 2026.', 'Code'),
  ('Budget room', 'pass', None, room('Other Direct Costs'), 'Code'),
  ('Necessary, reasonable and for this project', 'pass', 'Supports', 'A boat for sampling in Example Bay, the project site.', 'Agent'),
], [
  (approx('Total, $1,480.00'), 'boat_rental_receipt.jpg · Gmail, Apr 12, 2026'),
  (approx('Example Marina, Jan 14, 2026'), 'boat_rental_receipt.jpg · Gmail, Apr 12, 2026'),
], [
  ('Jan 16, 2026', 'Ledger line L-1015 arrived. ' + to('missing') + ': no bill yet.'),
  ('Apr 12, 2026', 'Receipt photo arrived. ' + arrow('missing', 'complete') + '.'),
])
S['L-1001'] = section('L-1001', [
  ('Period of performance', 'pass', None, 'Bought Nov 12, 2025, inside the period.', 'Code'),
  ('Evidence checklist', 'pass', '1 of 1 filled', 'A bill that adds up (account default): invoice INV-1001, $1,240.00 of $1,240.00. It arrived two days before the ledger line and waited, unlinked.', 'Code'),
  ('Budget room', 'pass', None, room('Materials and Supplies') + ' Line assigned by the agent.', 'Code'),
  ('Necessary, reasonable and for this project', 'pass', 'Supports', 'Core liners for sampling sediment, the project’s fieldwork.', 'Agent'),
], [
  (q('Sediment core liners, 50 count: $1,240.00'), 'invoice_1001.txt, line 9 · upload, Nov 12, 2025'),
  (q('Total Due: $1,240.00'), 'invoice_1001.txt, line 11 · upload, Nov 12, 2025'),
], [
  ('Nov 14, 2025', 'Ledger line L-1001 arrived. ' + to('complete') + '.'),
])

def page(n, inner):
    return f'''<section class="ft-rpage" id="rp-{n}" aria-label="Page {n} of 9">
  <header class="ft-rpage__head"><span>Evidence report &middot; <span class="ft-id">SYN-2300117</span> &middot; Sediment Microbiome Survey of Example Bay</span><span><span class="ft-rdraft">Draft</span> <span class="ft-rasof">As of Apr 12, 2026</span></span></header>
  <div class="ft-rpage__body">{inner}</div>
  <footer class="ft-rpage__foot"><span>Prepared with FundTrail. All data in this demo is synthetic.</span><span>Page {n} of 9</span></footer>
</section>
'''
lead = '<p class="ft-rx__lead"><span class="ft-rx__kicker">Charges, one section each</span> The checks code ran, the quoted evidence, the answers with who gave them, the accountant’s decisions, and each change of bucket.</p>'
more = '<p class="ft-rx__more">Sections for the other 45 charges follow in the same layout.</p>'
out = page(4, lead + S['L-1002'] + S['L-0981']) + page(5, S['L-1010'] + S['L-1019']) + page(6, S['L-1015'] + S['L-1001'] + more)
open(root + '/components/_src/report-sections.html', 'w').write(out)
print('sections written', len(out))
