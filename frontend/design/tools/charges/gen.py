# Build the Charges card from report-data.json. Nothing is retyped: rows, amounts, lines and counts come from the data;
# the six charges the demo tells a story about get their trail from the Demo's end state (Apr 12, 2026).
import json, os, sys, datetime as dt, subprocess
from pathlib import Path as _P
S = str(next(p for p in _P(__file__).resolve().parents if (p / 'system').is_dir() and (p / 'tools').is_dir()))  # frontend/design
root = S + '/system'
d = json.load(open(root + '/components/_src/report-data.json'))

def fdate(x): return x.strftime('%b ') + str(x.day) + x.strftime(', %Y')
def T(kind, title, verdict, what='', **extra):
    n = {'kind': kind, 'title': title, 'verdict': verdict, 'what': what}; n.update(extra); return n

KIND = {'receipt_': 'Receipt', 'invoice_': 'Invoice', 'psc_receipt_': 'Participant receipt'}
def kind_of(src):
    for p in ('psc_receipt_', 'receipt_', 'invoice_'):
        if src.startswith(p): return KIND[p]
    return 'File'

known = {
 'L-1002': dict(
   trail=[T('charge', 'Ledger line L-1002', 'Charged', '$2,180.00 to Other Direct Costs, work done Feb 20, 2026'),
          T('ok', 'Invoice SEQ-0207', 'Amount matches', 'Example Sequencing Core, $2,180.00 of $2,180.00', source=True),
          T('ok', 'Email from Dr. Robin Example', 'Known sender', 'The principal investigator forwarded the invoice, Feb 21', source=True),
          T('ok', 'Necessary, reasonable and for this project', 'Agent supports', 'The agent read the invoice against the award.', source=True),
          T('replaced', 'Award letter', 'End date superseded', 'Its end date, Jan 31, 2026, no longer applies.', source=True),
          T('ok', 'Amendment 01', 'Confirmed', 'The grant now ends Jan 31, 2027. Confirmed by the accountant, Apr 10, 2026.', source=True)],
   history=[dict(date='Apr 10, 2026', trigger='New end date confirmed', frm='conflict', to='complete', by='Confirmed by the accountant, Apr 10, 2026.'),
            dict(date='Feb 24, 2026', trigger='Ledger line L-1002 arrived', to='conflict')],
   covers=[dict(file='sequencing_invoice.eml', kind='Invoice SEQ-0207, in an email from the principal investigator', uses='$2,180.00 of $2,180.00', open=['F3', 'Total'])]),
 'L-0981': dict(
   trail=[T('charge', 'Ledger line L-0981', 'Charged', '$650.00 to Participant Support Costs, Oct 3, 2025'),
          T('ok', 'Registration receipt', 'Amount matches', 'Example Ocean Sciences Meeting, $650.00 of $650.00', source=True),
          T('fail', 'Approval email', 'Wrong approver', 'Approved by the principal investigator by email. The award needs the program officer.', source=True, quote='Approved, go ahead and register.', loc='approval_email.eml'),
          T('missing', "Program officer's approval", 'Not on file', 'Written approval through Research.gov, required for participant support costs.')],
   history=[dict(date='Oct 6, 2025', trigger='Approval email arrived', frm='missing', to='conflict')],
   covers=[dict(file='registration_receipt.pdf', kind='Receipt', uses='$650.00 of $650.00'),
           dict(file='approval_email.eml', kind='Approval, from the principal investigator', uses='Wrong approver', open=['F4', 'Approval'], short=True)]),
 'L-1010': dict(
   trail=[T('charge', 'Ledger line L-1010', 'Charged', '$5,833.33 to Other Direct Costs, Jan 9, 2026'),
          T('human', 'Invoice SEQ-0311', 'Split unknown', 'Example Sequencing Core, $10,000.00 for a run shared with another grant', source=True),
          T('missing', "This grant's part", 'Not on file', 'Nothing on file gives the split. Enter it, or find an email or itemized invoice that does.', action='split')],
   history=[dict(date='Jan 13, 2026', trigger='Ledger line L-1010 arrived', to='human')],
   covers=[dict(file='invoice_SEQ-0311.pdf', kind='Invoice, shared with SYN-2300245', uses="This grant's part of $10,000.00 isn't on file", open=['F5', 'Total'], short=True)]),
 'L-1019': dict(
   trail=[T('charge', 'Ledger line L-1019', 'Charged', '$1,325.00 to Materials and Supplies, Jan 21, 2026'),
          T('ok', 'Receipt photo', 'Amount matches', 'Example Optics Supply, $1,325.00 of $1,325.00, box checked by a second look', source=True),
          T('human', 'Is it for this project?', 'Agent unsure', 'The receipt names a field camera, but nothing on file ties it to the sediment survey.', source=True, action='answer')],
   history=[dict(date='Jan 23, 2026', trigger='Ledger line L-1019 arrived', to='human')],
   covers=[dict(file='field_camera_receipt.jpg', kind='Receipt photo, box checked by a second look', uses='$1,325.00 of $1,325.00', open=['F7', 'Total'])]),
 'L-1015': dict(
   trail=[T('charge', 'Ledger line L-1015', 'Charged', '$1,480.00 to Other Direct Costs, Jan 14, 2026'),
          T('ok', 'Receipt photo', 'Amount matches', 'Example Marina, $1,480.00 of $1,480.00, box checked by a second look', source=True),
          T('ok', 'Necessary, reasonable and for this project', 'Agent supports', 'A boat for sampling in Example Bay, the project site', source=True)],
   history=[dict(date='Apr 12, 2026', trigger='Receipt photo arrived', frm='missing', to='complete'),
            dict(date='Jan 16, 2026', trigger='Ledger line L-1015 arrived', to='missing')],
   covers=[dict(file='boat_rental_receipt.jpg', kind='Receipt photo, box checked by a second look', uses='$1,480.00 of $1,480.00', open=['F6', 'Total'])]),
 'L-1001': dict(
   trail=[T('charge', 'Ledger line L-1001', 'Charged', '$1,240.00 to Materials and Supplies, Nov 12, 2025'),
          T('ok', 'Invoice INV-1001', 'Amount matches', 'Example Lab Supply Co., $1,240.00 of $1,240.00', source=True),
          T('ok', 'Necessary, reasonable and for this project', 'Agent supports', 'Sediment core liners for the survey.', source=True),
          T('ok', 'Period of performance', 'In the period', 'Bought Nov 12, 2025, inside Feb 1, 2023 to Jan 31, 2027.')],
   history=[dict(date='Nov 14, 2025', trigger='Ledger line L-1001 arrived', to='complete')],
   covers=[dict(file='invoice_1001.txt', kind='Invoice INV-1001, uploaded Nov 12, 2025', uses='$1,240.00 of $1,240.00')]),
}

BILL = 'A bill that adds up to the charge'
def item(name, state='filled', **kw):
    # The bills list right under the checklist names the file and the amount, so a filled bill item stays one short line
    return dict(need=BILL, by='default', state=state)
def E(who, date, text, kind='comment', **kw):
    e = dict(who=who, date=date, text=text, kind=kind); e.update(kw); return e
story = {
 'L-1002': dict(checklist=[item('Invoice SEQ-0207')], thread=[
    E('code', 'Feb 24, 2026', 'Work done Feb 20, 2026, after the end date in force, Jan 31, 2026.', 'reason', result='fails'),
    E('agent', 'Apr 10, 2026', "Amendment 01 moves the end date to Jan 31, 2027. It's waiting for you on the problem list. Once you confirm it, this charge passes.",
      quote=dict(text='changed from January 31, 2026 to January 31, 2027', loc='extension_notice.txt, line 8')),
    E('you', 'Apr 10, 2026', 'Confirmed amendment 01.', 'decision'),
    E('code', 'Apr 10, 2026', 'Work done inside the period, which now ends Jan 31, 2027.', 'reason', result='passes')]),
 'L-0981': dict(checklist=[item('Registration receipt'),
    dict(need="Program officer's written approval, through Research.gov", by='code', state='missing', expected='Oct 3, 2025')], thread=[
    E('code', 'Oct 6, 2025', "Approved by the principal investigator by email. Using participant support money for this needs the program officer's written approval, through Research.gov.", 'reason', result='fails'),
    E('agent', 'Oct 6, 2025', "The email is Dr. Robin Example's reply to Sam Example. No approval from the program officer is on file.")]),
 'L-1010': dict(checklist=[dict(need=BILL, by='default', state='partial', note="Invoice SEQ-0311 is linked, but this grant's part isn't on file")], thread=[
    E('code', 'Jan 13, 2026', "Invoice SEQ-0311 is for $10,000.00 and this charge is $5,833.33. Nothing on file gives this grant's part.", 'reason'),
    E('agent', 'Jan 13, 2026', 'The invoice says the run is shared by SYN-2300117 and SYN-2300245. No email on file gives the split.')]),
 'L-1019': dict(checklist=[item('Receipt photo')], thread=[
    E('agent', 'Jan 23, 2026', 'The receipt names a field camera, but nothing on file ties it to the sediment survey.', 'answer', answer='unsure')]),
 'L-1015': dict(checklist=[item('Receipt photo')], thread=[
    E('code', 'Jan 16, 2026', 'No bill on file for $1,480.00.', 'reason', result='missing'),
    E('code', 'Mar 17, 2026', "Missing for 60 days, so it's on the problem list.", 'reason'),
    E('agent', 'Apr 12, 2026', 'Linked the receipt photo from Example Marina, $1,480.00 of $1,480.00.'),
    E('code', 'Apr 12, 2026', 'A bill covers $1,480.00 of $1,480.00.', 'reason', result='passes')]),
 'L-1001': dict(checklist=[item('Invoice INV-1001')], thread=[
    E('code', 'Nov 14, 2025', 'A bill covers $1,240.00 of $1,240.00, inside the period.', 'reason', result='passes')]),
}

rows = []
for c in d['charges']:
    r = dict(id=c['id'], date=c['dateText'], iso=c['date'], name=c['desc'], vendor=c['vendor'], line=c['line'], cents=c['cents'],
             amount=c['amount'], bucket=c['bucket'], reason=c['reason'], source=c['source'])
    if c['id'] in known:
        r.update(known[c['id']])
    else:
        day = dt.date.fromisoformat(c['date']); n = int(c['id'][2:])
        posting = day + dt.timedelta(days=2); arrived = day + dt.timedelta(days=n % 7 + 2)
        kind = kind_of(c['source']); num = c['source'].split('_')[-1].split('.')[0]
        r['trail'] = [T('charge', 'Ledger line ' + c['id'], 'Charged', c['amount'] + ' to ' + c['line'] + ', ' + c['dateText']),
                      T('ok', kind + ' ' + num, 'Amount matches', c['vendor'] + ', ' + c['amount'] + ' of ' + c['amount'], source=True),
                      T('ok', 'Necessary, reasonable and for this project', 'Agent supports', '', source=True),
                      T('ok', 'Period of performance', 'In the period', '')]
        if arrived <= posting:
            r['history'] = [dict(date=fdate(posting), trigger='Ledger line ' + c['id'] + ' arrived', to='complete')]
        else:
            r['history'] = [dict(date=fdate(arrived), trigger=kind + ' ' + num + ' arrived', frm='missing', to='complete'),
                            dict(date=fdate(posting), trigger='Ledger line ' + c['id'] + ' arrived', to='missing')]
        r['covers'] = [dict(file=c['source'], kind=kind + ', ' + ('Gmail' if kind == 'Invoice' else 'uploaded') + ' ' + fdate(arrived), uses=c['amount'] + ' of ' + c['amount'])]
    r['account'] = c['line']  # the ledger's own account; the demo ledger uses the budget line names
    if c['id'] in story: r.update(story[c['id']])
    else:
        bill = r['covers'][0]['file']; kind = kind_of(c['source']); num = c['source'].split('_')[-1].split('.')[0]
        r['checklist'] = [item(kind + ' ' + num)]
        r['thread'] = [E('code', r['history'][0]['date'], 'A bill covers ' + c['amount'] + ' of ' + c['amount'] + ', inside the period.', 'reason', result='passes')]
    rows.append(r)

def cents(s): return int(round(float(s.replace('$', '').replace(',', '')) * 100))
def money(c): return '${:,.2f}'.format(c / 100)
budget = []
for b in d['grant']['budget']:
    bc, ch = cents(b['budget']), cents(b['charged'])
    assert ch == sum(r['cents'] for r in rows if r['line'] == b['line']), b['line']
    budget.append(dict(line=b['line'], key={'Materials and Supplies': 'ms', 'Other Direct Costs': 'odc', 'Participant Support Costs': 'psc'}[b['line']],
                       budget=b['budget'], charged=b['charged'], left=money(bc - ch), pct=round(ch / bc, 4)))
assert sum(r['cents'] for r in rows) == 9641218 and len(rows) == 51
data = dict(grant=d['grant'], counts=d['counts'], budget=budget, charges=rows)
t = open(S + '/tools/charges/template.html').read()
t = t.replace('/*@DATA@*/null', json.dumps(data, separators=(',', ':')).replace('</', '<\\/'))
os.makedirs(root + '/components/Charges', exist_ok=True)
open(root + '/components/Charges/preview.html', 'w').write(t)
subprocess.run(['python3', S + '/tools/inline_viewer.py', root, 'Charges'], check=True, stdout=subprocess.DEVNULL)
subprocess.run(['python3', S + '/tools/inline_pr6.py', root, 'Charges'], check=True, stdout=subprocess.DEVNULL)
subprocess.run(['python3', S + '/tools/inline_menu.py', root, 'Charges'], check=True, stdout=subprocess.DEVNULL)
subprocess.run(['python3', S + '/tools/inline_layout.py', root, 'Charges'], check=True, stdout=subprocess.DEVNULL)
print('Charges built:', len(rows), 'charges,', money(sum(r['cents'] for r in rows)))
