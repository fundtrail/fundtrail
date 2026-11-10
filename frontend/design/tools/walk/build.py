# Build the Walkthrough card: every screen, in journey order, linked by its real buttons.
import json, os, subprocess, sys
from pathlib import Path as _P
S = str(next(p for p in _P(__file__).resolve().parents if (p / 'system').is_dir() and (p / 'tools').is_dir()))  # frontend/design
R = S + '/system'
SCREENS = [
 ('signin', 'Sign in', 'SignIn', '', 'Get in', 'Click Continue with Google. The first sign-in sets up the demo workspace, then opens it.'),
 ('home', 'Workspace home', 'Workspace', '', 'Workspace', 'Click Example Bay to open its grant, or Add a grant. Try the workspace name and Account in the sidebar.'),
 ('add', 'Add a grant', 'AddGrant', 'step=1', 'Workspace', 'Drop the letter, review the terms, confirm, drop the ledger, then the evidence.'),
 ('grant', 'Grant page', 'Demo', 's=0', 'Work the grant', 'Click through the rows: the details scroll on the right and the agent thread stays docked at the bottom. Ask on L-1019. Next arrival brings the extension; confirm it. Any link opens the viewer.'),
 ('charges', 'Charges', 'Charges', '', 'Work the grant', 'Every charge. Filter by bucket or budget line, search, and click a row.'),
 ('evidence', 'Evidence', 'Evidence', '', 'Work the grant', 'Every file. Click a fact to open it in the viewer. Not linked shows invoice 2050.'),
 ('terms', 'Grant terms', 'GrantTerms', '', 'Work the grant', 'Terms in force and what they replaced. Quotes open the viewer.'),
 ('closeout', 'Closeout', 'Closeout', '', 'Close out', 'Berkeley’s steps and the open charges. Preview opens the report; Sign off needs a note.'),
 ('report', 'Evidence report', 'EvidenceReport', '', 'Close out', 'The 9-page PDF the accountant attaches to the certification. Scroll through it.'),
 ('map', 'Screen map', 'ScreenMap', '', 'Overview', 'Every screen on one page, with the click that leads to the next.'),
]
NAV = r'''<script>
(function () {
  function go(id) { parent.postMessage({ ftGo: id }, '*'); }
  window.FTOpenWorkspace = function () { go('home'); };
  var SIDE = { 'Workspace': 'home', 'Problem list': 'grant', 'Charges': 'charges', 'Evidence': 'evidence', 'Grant terms': 'terms', 'Closeout': 'closeout', 'Example Bay': 'grant', 'Add a grant': 'add' };
  /* Only Example Bay has screens in this demo: say so instead of doing nothing */
  var OTHER = /Kelp Forest Survey|Tidal Marsh Carbon/;
  document.addEventListener('click', function (e) {
    var g = e.target.closest && e.target.closest('.ft-sidebar a.ft-nav__item, .ft-wh-row');
    if (g && OTHER.test(g.textContent) && !/Example Bay/.test(g.textContent)) { e.preventDefault(); e.stopPropagation(); parent.postMessage({ ftNote: 'Only Example Bay is built in this demo.' }, '*'); }
  }, true);
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a, button, [role="menuitem"], .ft-wh-row, tr, [data-grant]');
    if (!a) return;
    var txt = (a.childNodes[0] && a.childNodes[0].nodeType === 3 ? a.childNodes[0].textContent : a.textContent).trim();
    var full = a.textContent.trim();
    if (a.closest('.ft-sidebar') && a.matches('a.ft-nav__item')) { var k = Object.keys(SIDE).filter(function (n) { return txt.indexOf(n) === 0; })[0]; if (k) { e.preventDefault(); e.stopPropagation(); go(SIDE[k]); } return; }
    if (/^Sign out$/.test(full)) { setTimeout(function () { go('signin'); }, 600); return; }
    if (a.matches('button') && /^Evidence report$/.test(full) && a.closest('.ft-topbar')) { e.stopPropagation(); go('report'); return; }
    if (/^Open the problem list$/.test(full)) { e.preventDefault(); e.stopPropagation(); go('grant'); return; }
    if (/^Add a grant$/.test(full) && !a.closest('.ft-sidebar') && document.title.indexOf('Workspace') >= 0) { e.stopPropagation(); go('add'); return; }
    if (document.title.indexOf('Workspace') >= 0 && /Example Bay/.test(full) && !a.closest('.ft-sidebar') && !a.matches('button')) { e.stopPropagation(); go('grant'); return; }
  }, true);
  /* On the grant page, report where its clock is: Apr 9 is step 0, Apr 10 with the new end date waiting is 2, Apr 10 confirmed is 3, Apr 12 is 4 */
  if (document.title.indexOf('Demo') >= 0) {
    var last = null, timer = null;
    var report = function () {
      var c = document.getElementById('demo-clock'), nx = document.getElementById('demo-next'), tl = document.getElementById('demo-timeline'), wt = document.getElementById('demo-side-terms');
      if (!c) return;
      var d = c.textContent.trim(), st = null;
      if (nx && /Reading/.test(nx.textContent)) return;
      if (/Apr 9,/.test(d)) st = 0;
      else if (/Apr 10,/.test(d)) st = (tl && /(End date\s*Jan 31, 2027|Jan 31, 2027\s*End date)/.test(tl.textContent) && !(wt && !wt.hidden)) ? 3 : 2;
      else if (/Apr 12,/.test(d)) st = 4;
      if (st === null || st === last) return;
      last = st; parent.postMessage({ ftClock: { date: d, step: st } }, '*');
    };
    var watch = function () {
      var mo = new MutationObserver(function () { clearTimeout(timer); timer = setTimeout(report, 200); });
      ['demo-clock', 'demo-side-problems', 'demo-side-terms', 'demo-timeline', 'demo-next'].forEach(function (id) { var el = document.getElementById(id); if (el) mo.observe(el, { childList: true, subtree: true, characterData: true, attributes: true }); });
      setTimeout(report, 400);
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', watch); else watch();
  }
})();
</script>'''
data = {}
for scr in SCREENS:
    sid, label, card, h, stage, hint = scr[:6]; extra = scr[6] if len(scr) > 6 else None
    for th in ('light', 'dark'):
        os.makedirs(S + '/build/shots', exist_ok=True); out = S + '/build/shots/walk-%s-%s.html' % (card, th)
        subprocess.run(['python3', S + '/tools/harness.py', R, out, card, th], check=True, capture_output=True)
        doc = open(out).read()
        add = NAV
        if extra and os.path.exists(S + '/tools/chat/' + extra): add += '<script>\n' + open(S + '/tools/chat/' + extra).read() + '\n</script>'
        i = doc.rfind('</body>'); doc = doc[:i] + add + doc[i:] if i > 0 else doc + add
        data[sid + ':' + th] = doc
meta = [dict(id=x[0], label=x[1], card=x[2], hash=x[3], stage=x[4], hint=x[5]) for x in SCREENS]
blob = json.dumps(data).replace('</', '<\\/')
page = open(S + '/tools/walk/template.html').read().replace('/*CLOCK*/', open(S + '/tools/walk/shell-clock.js').read()).replace('/*META*/', json.dumps(meta)).replace('/*DOCS*/', blob)
os.makedirs(R + '/components/Walkthrough', exist_ok=True)
open(R + '/components/Walkthrough/preview.html', 'w').write(page)
print('Walkthrough', len(page) // 1024, 'KB')
