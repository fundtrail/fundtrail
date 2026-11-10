# Build report page 1 (summary) from report-data.json. Numbers are read, never retyped.
import json, html, sys
root = sys.argv[1]
D = json.load(open(root + '/components/_src/report-data.json'))
g, n, ch = D['grant'], D['counts'], D['charges']
e = html.escape
def cents(s): return int(round(float(s.replace('$', '').replace(',', '')) * 100))
def money(c): return '${:,.2f}'.format(c / 100)
total = sum(c['cents'] for c in ch)
assert money(total) == g['charged']
count = len(ch)
budget_rows, tb, tc = '', 0, 0
for b in g['budget']:
    bb, cc = cents(b['budget']), cents(b['charged']); tb += bb; tc += cc
    budget_rows += f'<tr><td>{e(b["line"])}</td><td class="num">{money(bb)}</td><td class="num">{money(cc)}</td><td class="num">{money(bb - cc)}</td></tr>'
assert tc == total and money(tb) == g['awarded']
buckets = [('complete', 'Evidence complete', n['complete']), ('conflict', 'Possible conflict', n['conflict']), ('human', 'Needs a human', n['human']), ('missing', 'Missing evidence', n['missing'])]
bucket_html = ''.join(f'<li class="ft-rs-bucket"><span class="ft-rs-mark ft-rs-mark--{k}" aria-hidden="true"></span><span class="ft-rs-bucket__n">{v}</span><span class="ft-rs-bucket__name">{name}</span></li>' for k, name, v in buckets)
page = f'''<section class="ft-rpage" id="rp-1" aria-label="Page 1 of 9">
  <header class="ft-rpage__head"><span>Evidence report · <span class="ft-id">{e(g["award"])}</span> · {e(g["title"])}</span><span class="ft-rs-asof"><span class="ft-rdraft">Draft</span> <span class="ft-rs-draft-text">As of {e(g["asOf"])}</span><span class="ft-rs-signed-text">Signed off {e(g["asOf"])}</span></span></header>
  <div class="ft-rpage__body ft-rs">
    <div class="ft-rs-title">
      <p class="ft-rs-kicker">Evidence report</p>
      <h1>{e(g["title"])}</h1>
      <p class="ft-rs-sub"><span class="ft-id">{e(g["award"])}</span> · {e(g["funder"])} · {e(g["recipient"])}</p>
    </div>
    <div class="ft-rs-figures">
      <div class="ft-rs-figure ft-rs-figure--main"><span class="ft-rs-figure__label">Total of all charges</span><span class="ft-rs-figure__value">{money(total)}</span><span class="ft-rs-figure__note">Matches the ledger report. {count} charges.</span></div>
      <div class="ft-rs-figure"><span class="ft-rs-figure__label">Ready for closeout</span><span class="ft-rs-figure__value">{n["complete"]} <span class="ft-rs-of">of {count}</span></span><span class="ft-rs-figure__note">Charges in Evidence complete</span></div>
      <div class="ft-rs-figure"><span class="ft-rs-figure__label">Awarded</span><span class="ft-rs-figure__value">{e(g["awarded"])}</span><span class="ft-rs-figure__note">Direct costs</span></div>
    </div>
    <section class="ft-rs-block" aria-labelledby="rs-buckets"><h2 id="rs-buckets">Charges by bucket</h2><ul class="ft-rs-buckets">{bucket_html}</ul>
      <p class="ft-rs-note">The {n["conflict"] + n["human"] + n["missing"]} charges not in Evidence complete are listed on page 7, under Open at sign-off.</p></section>
    <section class="ft-rs-block" aria-labelledby="rs-award"><h2 id="rs-award">The award</h2>
      <dl class="ft-rkv">
        <dt>Award number</dt><dd><span class="ft-id">{e(g["award"])}</span></dd>
        <dt>Funder</dt><dd>{e(g["funder"])}</dd>
        <dt>Recipient</dt><dd>{e(g["recipient"])}</dd>
        <dt>Principal investigator</dt><dd>{e(g["pi"])}</dd>
        <dt>Period of performance</dt><dd>{e(g["period"])}<span class="ft-rs-dd-note">{e(g["periodNote"])}.</span></dd>
        <dt>Prepared for</dt><dd>Berkeley's Award Closeout Certification, due Mar 31, 2027. Attach it next to the CalAnswers ledger report.</dd>
        <dt>Status</dt><dd class="ft-rs-status-draft">Draft. Not signed off yet. It updates whenever a record changes.</dd><dd class="ft-rs-status-signed">Signed off by Taylor Example, {e(g["asOf"])}. See page 7.</dd>
      </dl></section>
    <section class="ft-rs-block" aria-labelledby="rs-budget"><h2 id="rs-budget">Budget by line</h2>
      <table class="ft-rtable ft-rs-budget"><thead><tr><th>Budget line</th><th class="num">Budget</th><th class="num">Charged</th><th class="num">Remaining</th></tr></thead>
      <tbody>{budget_rows}</tbody><tfoot><tr><td>Total</td><td class="num">{money(tb)}</td><td class="num">{money(tc)}</td><td class="num">{money(tb - tc)}</td></tr></tfoot></table></section>
    <section class="ft-rs-block ft-rs-howto" aria-labelledby="rs-howto"><h2 id="rs-howto">How to read this report</h2>
      <ul>
        <li><b>Checks</b> are run by code on the records: dates against the period, each charge's evidence checklist and whether its bills add up, the approver's role and channel, and budget room.</li>
        <li><b>Answers</b> to questions code can't settle are labeled with who wrote them, Agent or Accountant, with their reasoning. The accountant has the last word; their decisions show on the charge they changed, and conversations with the agent stay out.</li>
        <li><b>Quotes</b> are checked against their file: the exact line, the passage on its PDF page, or on photos a box checked by a second look. A fact that couldn't be confirmed says so.</li>
        <li><b>Pages 2 and 3</b> list every charge. <b>Pages 4 to 6</b> show the checks and evidence charge by charge. <b>Page 7</b> is the sign-off, and <b>pages 8 and 9</b> list every source file.</li>
      </ul></section>
  </div>
  <footer class="ft-rpage__foot"><span>Prepared with FundTrail. All data in this demo is synthetic.</span><span>Page 1 of 9</span></footer>
</section>
'''
open(root + '/components/_src/report-summary.html', 'w').write(page)
print('page 1 written', money(total), count, n)
