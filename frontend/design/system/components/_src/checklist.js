/* FundTrail evidence checklist (PR 6, decision 0011): what a charge should have, filled or missing, who added each item,
   and any removal the agent suggests, waiting for the accountant.
   FTChecklist.render(items, opts)          pure: returns HTML
   FTChecklist.summary(items)               {filled, missing, partial, waiting, total}
   FTChecklist.mount(container, items, opts) stateful: Accept, Reject, Undo and Add item, with an inline done line
     opts: {account, total:'$2,300.00', sum:{parts:['$1,800.00','$500.00'], total:'$2,300.00'}, title, onChange(items, action)}
   Item: {need, by:'default'|'code'|'agent'|'you', state:'filled'|'missing'|'partial', filledBy:{name, amount, of, note},
          period, expected, due:'late'|'not-due', rule:{kind:'adds-up'|'rate', math}, removal:{by:'agent', reason, state:'waiting'|'accepted'|'rejected'},
          removed:{by, note}} */
(function () {
  var C = window.FTChecklist = {};
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  var BY = { 'default': 'Account default', code: 'Added by code', agent: 'Added by the agent', you: 'Added by you' };
  var STATE = { filled: 'Filled', missing: 'Missing', partial: 'Not complete' };

  C.summary = function (items) {
    var s = { filled: 0, missing: 0, partial: 0, waiting: 0, total: 0 };
    items.forEach(function (it) {
      if (it.removed) return;
      s.total++; s[it.state] = (s[it.state] || 0) + 1;
      if (it.removal && it.removal.state === 'waiting') s.waiting++;
    });
    return s;
  };

  function itemHtml(it, i) {
    var removed = !!it.removed;
    var st = removed ? 'removed' : it.state;
    var stateText = removed ? 'Removed' : (it.state === 'missing' && it.due === 'not-due') ? 'Not due yet' : STATE[it.state];
    var detail = '';
    if (removed) detail = '<span class="ft-cl-detail">' + esc(it.removed.note) + '</span>';
    else if (it.filledBy) {
      detail = '<span class="ft-cl-detail"><span class="ft-cl-file">' + esc(it.filledBy.name) + '</span>' +
        (it.filledBy.amount ? ' <span class="ft-sep">&middot;</span> <span class="ft-amount">' + esc(it.filledBy.amount) + '</span>' + (it.filledBy.of ? ' of <span class="ft-amount">' + esc(it.filledBy.of) + '</span>' : '') : '') +
        (it.filledBy.note ? ' <span class="ft-sep">&middot;</span> ' + esc(it.filledBy.note) : '') + '</span>';
    } else if (it.state === 'missing') {
      detail = '<span class="ft-cl-detail">' + (it.expected ? (it.due === 'not-due' ? 'Expected ' : 'Expected since ') + esc(it.expected) : 'Nothing on file yet') + '</span>';
    } else if (it.note) detail = '<span class="ft-cl-detail">' + esc(it.note) + '</span>';
    var math = it.rule && it.rule.kind === 'rate' && it.rule.math && !removed ? '<span class="ft-cl-math">' + esc(it.rule.math) + ' <span class="ft-cl-checked">checked by code</span></span>' : '';
    var waiting = it.removal && it.removal.state === 'waiting' && !removed;
    var removal = waiting ? '<div class="ft-cl-removal" role="group" aria-label="The agent suggests removing ' + esc(it.need) + '">' +
      '<p class="ft-cl-removal__text"><span class="ft-cl-removal__who">Agent suggests removing this item.</span> ' + esc(it.removal.reason) + '</p>' +
      '<div class="ft-actions"><button type="button" class="ft-btn ft-btn--sm ft-btn--approve" data-cl-act="accept" data-cl-i="' + i + '">Accept</button>' +
      '<button type="button" class="ft-btn ft-btn--sm ft-btn--reject" data-cl-act="reject" data-cl-i="' + i + '">Reject</button></div></div>' : '';
    return '<li class="ft-cl-item is-' + st + (waiting ? ' has-removal' : '') + '" data-cl-i="' + i + '">' +
      '<span class="ft-cl-mark" aria-hidden="true"></span>' +
      '<div class="ft-cl-main"><span class="ft-cl-need">' + esc(it.need) + (it.period ? ' <span class="ft-cl-period">' + esc(it.period) + '</span>' : '') + '</span>' + detail + math + '</div>' +
      '<span class="ft-cl-meta"><span class="ft-cl-state">' + stateText + '</span><span class="ft-cl-by">' + (removed ? '' : BY[it.by]) + '</span></span>' +
      removal + '</li>';
  }

  C.render = function (items, opts) {
    opts = opts || {};
    var s = C.summary(items);
    var head = '<div class="ft-cl-head"><span class="ft-cl-title">' + esc(opts.title || 'Evidence needed') + '</span>' +
      '<span class="ft-cl-count">' + s.filled + ' of ' + s.total + ' filled' + (s.waiting ? ' <span class="ft-sep">&middot;</span> ' + s.waiting + ' waiting for you' : '') + '</span>' +
      (opts.account ? '<span class="ft-cl-account">Ledger account: ' + esc(opts.account) + '</span>' : '') + '</div>';
    var list = '<ul class="ft-cl-list">' + items.map(itemHtml).join('') + '</ul>';
    var sum = opts.sum ? '<p class="ft-cl-sum">' + opts.sum.parts.map(esc).join(' + ') + ' = <span class="ft-amount">' + esc(opts.sum.total) + '</span> <span class="ft-sep">&middot;</span> adds up to the charge <span class="ft-cl-checked">checked by code</span></p>' : '';
    var add = opts.adding ? '<form class="ft-cl-add" data-cl-form="add"><label class="ft-sr-only" for="' + opts.uid + '-add">New item</label>' +
      '<input class="ft-input" id="' + opts.uid + '-add" name="need" placeholder="For example: Signed honorarium letter" autocomplete="off" value="' + esc(opts.draft || '') + '">' +
      '<button class="ft-btn ft-btn--sm" type="submit">Add</button><button class="ft-overrule" type="button" data-cl-act="cancel">Cancel</button></form>'
      : '<button type="button" class="ft-overrule ft-cl-addbtn" data-cl-act="add">Add item</button>';
    var done = opts.done ? '<div class="ft-trail__done ft-cl-done" role="status" tabindex="-1"><span>' + esc(opts.done) + '</span><button type="button" data-cl-act="undo">Undo</button></div>' : '';
    return '<section class="ft-cl" aria-label="' + esc(opts.title || 'Evidence needed') + '">' + head + list + sum + done + '<div class="ft-cl-foot">' + add + '</div></section>';
  };

  var uidN = 0;
  C.mount = function (container, items, opts) {
    opts = opts || {};
    var st = { items: items, done: null, undo: null, adding: false, draft: '' };
    var uid = 'ftcl' + (++uidN);
    function clone(x) { return JSON.parse(JSON.stringify(x)); }
    function draw(focusSel) {
      container.innerHTML = C.render(st.items, { account: opts.account, sum: opts.sum, title: opts.title, done: st.done, adding: st.adding, draft: st.draft, uid: uid });
      var t = focusSel && container.querySelector(focusSel);
      if (t) t.focus();
    }
    function act(text, before, focusSel) { st.undo = before; st.done = text; draw(focusSel || '.ft-cl-done'); if (opts.onChange) opts.onChange(st.items); }
    container.addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('[data-cl-act]') : null; if (!b || !container.contains(b)) return;
      var a = b.getAttribute('data-cl-act'), i = parseInt(b.getAttribute('data-cl-i'), 10), before = clone(st.items);
      if (a === 'accept') {
        var it = st.items[i]; it.removal.state = 'accepted'; it.removed = { by: 'you', note: 'Removed by you, accepting the agent’s suggestion: ' + it.removal.reason };
        act('Removed “' + it.need + '”. Code rechecks the charge without it.', before);
      } else if (a === 'reject') {
        var r = st.items[i]; r.removal.state = 'rejected';
        act('Kept “' + r.need + '”. The agent can’t suggest this again unless new evidence arrives.', before);
      } else if (a === 'undo') {
        var back = st.undo; st.items = back; st.undo = null; st.done = null; draw('[data-cl-act="accept"], [data-cl-act="add"]');
        if (opts.onChange) opts.onChange(st.items);
      } else if (a === 'add') { st.adding = true; st.draft = ''; draw('#' + uid + '-add'); }
      else if (a === 'cancel') { st.adding = false; draw('[data-cl-act="add"]'); }
    });
    container.addEventListener('input', function (e) { if (e.target.name === 'need' && container.contains(e.target)) st.draft = e.target.value; });
    container.addEventListener('submit', function (e) {
      if (!container.contains(e.target)) return; e.preventDefault();
      var v = st.draft.trim(); if (!v) { var inp = container.querySelector('#' + uid + '-add'); if (inp) inp.focus(); return; }
      var before = clone(st.items); st.items.push({ need: v, by: 'you', state: 'missing', expected: opts.today || null });
      st.adding = false; st.draft = '';
      act('Added “' + v + '”. It takes effect right away.', before);
    });
    draw();
    return { state: st, draw: draw };
  };
})();
