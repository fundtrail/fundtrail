# Report pages 2 and 3: every charge in date order. Generated from components/_src/report-data.json; never retype rows.
# usage: gen_table.py <design system root> [rows on page 2]
import json, os, sys, html
root = sys.argv[1]
first = int(sys.argv[2]) if len(sys.argv) > 2 else 26
d = json.load(open(os.path.join(root, 'components/_src/report-data.json')))
g = d['grant']
rows = sorted(d['charges'], key=lambda c: (c['date'], c['id']))
assert len(rows) == 51
total = sum(c['cents'] for c in rows)
money = '${:,.2f}'.format(total / 100)
assert money == g['charged'], (money, g['charged'])
NAME = {'complete': 'Evidence complete', 'conflict': 'Possible conflict', 'human': 'Needs a human', 'missing': 'Missing evidence'}
e = lambda s: html.escape(str(s), quote=True)
open_rows = [c for c in rows if c['bucket'] != 'complete']

def head():
    return ('<header class="ft-rpage__head"><span>Evidence report · <span class="ft-id">' + e(g['award']) + '</span> · ' + e(g['title']) + '</span>'
            '<span><span class="ft-rdraft">Draft</span> <span class="ft-rt-asof">As of ' + e(g['asOf']) + '</span><span class="ft-rt-signedon">Signed off ' + e(g['asOf']) + '</span></span></header>')
def foot(n):
    return '<footer class="ft-rpage__foot"><span>Prepared with FundTrail. All data in this demo is synthetic.</span><span>Page ' + str(n) + ' of 9</span></footer>'
COLS = ('<colgroup><col class="ft-rt-c-date"><col class="ft-rt-c-line"><col class="ft-rt-c-desc"><col class="ft-rt-c-budget">'
        '<col class="ft-rt-c-amount"><col class="ft-rt-c-bucket"><col class="ft-rt-c-reason"></colgroup>')
THEAD = ('<thead><tr><th scope="col">Date</th><th scope="col">Ledger line</th><th scope="col">Description</th><th scope="col">Budget line</th>'
         '<th scope="col" class="num">Amount</th><th scope="col">Bucket</th><th scope="col">Reason</th></tr></thead>')
def row(c):
    op = c['bucket'] != 'complete'
    cls = 'ft-rt-row' + (' is-open is-' + c['bucket'] if op else '')
    mark = '<span class="ft-rt-mark ft-rt-mark--' + c['bucket'] + '" aria-hidden="true"></span>' if op else ''
    return ('<tr class="' + cls + '"><td class="ft-rt-date">' + e(c['dateText']) + '</td><td><span class="ft-id">' + e(c['id']) + '</span></td>'
            '<td class="ft-rt-desc">' + e(c['desc']) + '</td><td class="ft-rt-budget">' + e(c['line']) + '</td><td class="num">' + e(c['amount']) + '</td>'
            '<td class="ft-rt-bucket">' + mark + e(NAME[c['bucket']]) + '</td><td class="ft-rt-reason">' + e(c['reason']) + '</td></tr>')
def table(part, label, foot_row=''):
    return ('<table class="ft-rtable ft-rt" aria-label="' + e(label) + '">' + COLS + THEAD + '<tbody>' + ''.join(row(c) for c in part) + '</tbody>' + foot_row + '</table>')

n_open = len(open_rows)
intro = ('<div class="ft-rt-intro"><h2>All charges</h2><p>' + str(len(rows)) + ' charges in date order, ' + e(g['charged']) + ' in all. '
         + ('The ' + str(n_open) + ' that aren’t Evidence complete are marked and shaded, and listed again on page 7.' if n_open else 'Every charge is Evidence complete.') + '</p></div>')
tfoot = ('<tfoot><tr><td colspan="4">Total, ' + str(len(rows)) + ' charges</td><td class="num">' + e(g['charged']) + '</td><td colspan="2" class="ft-rt-tnote">Matches the ledger report</td></tr></tfoot>')
legend = ('<p class="ft-rt-legend"><span><span class="ft-rt-mark ft-rt-mark--conflict" aria-hidden="true"></span>Possible conflict</span>'
          '<span><span class="ft-rt-mark ft-rt-mark--human" aria-hidden="true"></span>Needs a human</span>'
          '<span><span class="ft-rt-mark ft-rt-mark--missing" aria-hidden="true"></span>Missing evidence</span>'
          '<span>Unmarked rows are Evidence complete.</span></p>')
p2 = ('<section class="ft-rpage ft-rt-page" id="rp-2" aria-label="Page 2 of 9">' + head() + '<div class="ft-rpage__body">' + intro
      + table(rows[:first], 'All charges, ' + rows[0]['dateText'] + ' to ' + rows[first - 1]['dateText']) + '</div>' + foot(2) + '</section>\n')
p3 = ('<section class="ft-rpage ft-rt-page" id="rp-3" aria-label="Page 3 of 9">' + head() + '<div class="ft-rpage__body"><div class="ft-rt-intro"><h2>All charges, continued</h2></div>'
      + table(rows[first:], 'All charges, ' + rows[first]['dateText'] + ' to ' + rows[-1]['dateText'], tfoot) + legend + '</div>' + foot(3) + '</section>\n')
out = os.path.join(root, 'components/_src/report-table.html')
open(out, 'w').write(p2 + p3)
print('wrote', out, 'page 2 rows', first, 'page 3 rows', len(rows) - first, 'open', [c['id'] for c in open_rows])
