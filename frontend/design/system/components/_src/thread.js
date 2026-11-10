/* FundTrail review thread: one charge's (or one record's) conversation. Code's reasons, the agent's comments,
   suggestions and disputes, the accountant's replies and decisions, and a box to ask the agent.
   FTThread.render(thread, opts)            returns HTML for a thread
   FTThread.bind(container, thread, opts)   draws it into container and wires Accept, Reject, Undo and Ask
   thread: { id, about: 'L-1019', entries: [entry] }
   entry:  { who: 'code'|'agent'|'you', date, text, kind: 'reason'|'comment'|'suggestion'|'dispute'|'answer'|'decision',
             result?: 'fails'|'passes'|'missing', answer?: 'supports'|'contradicts'|'unsure',
             quote?: { text, loc }, change?: { now, suggested }, check?: 'the check a dispute names',
             effect?: 'what accepting does', state?: 'waiting'|'accepted'|'rejected', decided?: date, pending?: true }
   opts:   { heading: 'Thread', ask: true, today: 'Apr 12, 2026', undoMs: 8000,
             onAccept(entry), onReject(entry), onUndo(entry, was), onAsk(question, reply(entry)) }
   Plain ES5, no dependencies. */
(function () {
  var T = window.FTThread = window.FTThread || {};
  var WHO = { code: 'Code', agent: 'Agent', you: 'You' };
  var RESULT = { fails: 'Fails', passes: 'Passes', missing: 'Missing' };
  var ANSWER = { supports: 'Supports', contradicts: 'Contradicts', unsure: 'Unsure' };
  var seq = 0;
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  function boxHtml(e, i, tid) {
    var head = e.kind === 'dispute' ? 'Dispute' : 'Suggestion', st = e.state || 'waiting';
    var h = '<div class="ft-th__box is-' + st + '" role="group" aria-labelledby="' + tid + '-bh' + i + '">' +
      '<p class="ft-th__boxhead" id="' + tid + '-bh' + i + '"><span>' + head + '</span>' +
      (st === 'waiting' ? '<span class="ft-th__boxstate">waiting for you</span>' : '') + '</p>';
    if (e.kind === 'dispute' && e.check) h += '<p class="ft-th__check">Disputes the check: <b>' + esc(e.check) + '</b></p>';
    if (e.change) h += '<dl class="ft-th__change"><dt>Now</dt><dd>' + esc(e.change.now) + '</dd><dt>Suggested</dt><dd>' + esc(e.change.suggested) + '</dd></dl>';
    if (e.effect && st === 'waiting') h += '<p class="ft-th__effect">' + esc(e.effect) + '</p>';
    if (st === 'waiting') {
      h += '<div class="ft-th__actions"><button type="button" class="ft-btn ft-btn--sm ft-btn--approve ft-btn--main" data-th-act="accept" data-th-i="' + i + '">Accept</button>' +
        '<button type="button" class="ft-btn ft-btn--sm ft-btn--reject" data-th-act="reject" data-th-i="' + i + '">Reject</button></div>';
    } else {
      h += '<p class="ft-th__decided" tabindex="-1" id="' + tid + '-dec' + i + '">' + (st === 'accepted' ? 'Accepted' : 'Rejected') + ' by you' + (e.decided ? ', ' + esc(e.decided) : '') + '.' +
        (st === 'rejected' ? ' The agent can raise it again only if new evidence arrives.' : '') + '</p>';
    }
    if (e.undo) h += '<div class="ft-trail__done ft-th__done" role="status"><span>' + esc(e.undo) + '</span><button type="button" data-th-act="undo" data-th-i="' + i + '">Undo</button></div>';
    return h + '</div>';
  }

  function entryHtml(e, i, tid) {
    if (e.pending) {
      return '<li class="ft-th__entry ft-th__entry--agent is-pending"><span class="ft-th__mark ft-th__mark--agent" aria-hidden="true"></span>' +
        '<div class="ft-th__meta"><span class="ft-th__who">Agent</span></div>' +
        '<p class="ft-th__body"><span class="ft-working"><span class="ft-working-dot" aria-hidden="true"></span>Agent is reading this charge</span></p></li>';
    }
    var who = e.who || 'agent';
    var lead = '';
    if (e.result) lead = '<b class="ft-th__result ft-th__result--' + e.result + '">' + RESULT[e.result] + '.</b> ';
    if (e.answer) lead = '<b class="ft-chip ft-chip--' + e.answer + '">' + ANSWER[e.answer] + '.</b> ';
    var h = '<li class="ft-th__entry ft-th__entry--' + who + (e.kind === 'decision' ? ' is-decision' : '') + '">' +
      '<span class="ft-th__mark ft-th__mark--' + who + '" aria-hidden="true"></span>' +
      '<div class="ft-th__meta"><span class="ft-th__who">' + WHO[who] + '</span>' + (e.date ? '<span class="ft-th__date">' + esc(e.date) + '</span>' : '') + '</div>';
    if (e.text) h += '<p class="ft-th__body">' + lead + esc(e.text) + '</p>';
    if (e.quote) h += '<p class="ft-th__quote">&ldquo;' + esc(e.quote.text) + '&rdquo; <span class="ft-loc">' + esc(e.quote.loc) + '</span></p>';
    if (e.kind === 'suggestion' || e.kind === 'dispute') h += boxHtml(e, i, tid);
    return h + '</li>';
  }

  T.render = function (thread, opts) {
    opts = opts || {};
    var tid = thread.uid || (thread.uid = 'ft-th-' + (++seq));
    var n = thread.entries.filter(function (e) { return !e.pending; }).length;
    var waiting = thread.entries.filter(function (e) { return (e.kind === 'suggestion' || e.kind === 'dispute') && (e.state || 'waiting') === 'waiting'; }).length;
    var h = '<section class="ft-th" aria-labelledby="' + tid + '-h">' +
      '<div class="ft-th__head"><h3 class="ft-th__title" id="' + tid + '-h">' + esc(opts.heading || 'Thread') + '</h3>' +
      '<span class="ft-th__count">' + n + ' ' + (n === 1 ? 'entry' : 'entries') + (waiting ? ' <span class="ft-sep">&middot;</span> <b class="ft-th__waiting">' + waiting + ' waiting for you</b>' : '') + '</span></div>' +
      '<ol class="ft-th__list" aria-label="' + esc((opts.heading || 'Thread') + (thread.about ? ', ' + thread.about : '')) + '">' +
      thread.entries.map(function (e, i) { return entryHtml(e, i, tid); }).join('') + '</ol>';
    if (opts.ask !== false) {
      var busy = thread.entries.some(function (e) { return e.pending; });
      h += '<form class="ft-th__ask" data-th-ask novalidate><label class="ft-th__asklabel" for="' + tid + '-q">Ask the agent about ' + esc(thread.about || 'this charge') + '</label>' +
        '<div class="ft-th__askrow"><textarea class="ft-textarea ft-th__q" id="' + tid + '-q" name="q" rows="1" aria-describedby="' + tid + '-qn"' + (busy ? ' disabled' : '') + ' placeholder="' + esc(opts.placeholder || 'For example: what would close this?') + '">' + esc(thread.draft || '') + '</textarea>' +
        '<button type="submit" class="ft-btn ft-btn--sm"' + (busy ? ' disabled' : '') + '>Ask</button></div>' +
        '<p class="ft-th__note" id="' + tid + '-qn">It answers about ' + esc(thread.about || 'this charge') + ' only. If it proposes a change, the change comes back here as a suggestion for you to accept.</p></form>';
    }
    h += '<div class="ft-sr-only" role="status" aria-live="polite" id="' + tid + '-live">' + esc(thread.live || '') + '</div>';
    return h + '</section>';
  };

  T.bind = function (container, thread, opts) {
    opts = opts || {};
    var timers = {};
    function draw(focusSel) {
      var a = document.activeElement, q = container.querySelector('.ft-th__q');
      if (q) thread.draft = q.value;
      container.innerHTML = T.render(thread, opts);
      if (focusSel) { var f = container.querySelector(focusSel); if (f) f.focus(); }
      else if (a && !a.isConnected && container.contains(document.activeElement) === false && a.getAttribute && a.getAttribute('data-th-act')) {
        var h = container.querySelector('.ft-th__title'); if (h) { h.tabIndex = -1; h.focus(); }
      }
    }
    function decide(i, st) {
      var e = thread.entries[i]; e.state = st; e.decided = opts.today || '';
      e.undo = st === 'accepted' ? (e.kind === 'dispute' ? 'Dispute accepted. The check is set aside for this charge, with the agent’s reasoning as your note.' : 'Suggestion accepted. Code rechecks the charge.')
        : 'Rejected. It stays as it was.';
      draw('[data-th-act="undo"][data-th-i="' + i + '"]');
      if (st === 'accepted' && opts.onAccept) opts.onAccept(e); if (st === 'rejected' && opts.onReject) opts.onReject(e);
      clearTimeout(timers[i]);
      timers[i] = setTimeout(function () {
        var had = document.activeElement && document.activeElement.getAttribute && document.activeElement.getAttribute('data-th-i') === String(i);
        e.undo = null; draw(had ? '#' + thread.uid + '-dec' + i : null);
      }, opts.undoMs == null ? 8000 : opts.undoMs);
    }
    container.addEventListener('click', function (ev) {
      var b = ev.target.closest ? ev.target.closest('[data-th-act]') : null; if (!b || !container.contains(b)) return;
      var i = parseInt(b.getAttribute('data-th-i'), 10), act = b.getAttribute('data-th-act');
      if (act === 'accept') decide(i, 'accepted');
      else if (act === 'reject') decide(i, 'rejected');
      else if (act === 'undo') {
        var e = thread.entries[i], was = e.state; clearTimeout(timers[i]);
        e.state = 'waiting'; e.decided = null; e.undo = null;
        draw('[data-th-act="' + (was === 'accepted' ? 'accept' : 'reject') + '"][data-th-i="' + i + '"]');
        if (opts.onUndo) opts.onUndo(e, was);
      }
    });
    container.addEventListener('submit', function (ev) {
      if (!ev.target.hasAttribute || !ev.target.hasAttribute('data-th-ask')) return;
      ev.preventDefault();
      var q = container.querySelector('.ft-th__q'), text = q ? q.value.trim() : '';
      if (!text) { if (q) q.focus(); return; }
      thread.draft = ''; if (q) q.value = '';
      thread.entries.push({ who: 'you', kind: 'comment', date: opts.today || '', text: text });
      thread.entries.push({ pending: true });
      thread.live = 'Question sent. The agent is reading.';
      draw('#' + thread.uid + '-live');
      var h = container.querySelector('.ft-th__title'); if (h) { h.tabIndex = -1; h.focus(); }
      function reply(entry) {
        for (var k = thread.entries.length - 1; k >= 0; k--) if (thread.entries[k].pending) { thread.entries.splice(k, 1); break; }
        entry.who = entry.who || 'agent'; entry.date = entry.date || opts.today || ''; thread.entries.push(entry);
        thread.live = 'The agent answered: ' + (entry.text || '');
        var ae = document.activeElement, mine = !ae || ae === document.body || container.contains(ae);
        draw(mine ? '.ft-th__q' : null);
      }
      if (opts.onAsk) opts.onAsk(text, reply);
      else setTimeout(function () { reply({ kind: 'comment', text: 'Noted. I have nothing on file that answers that yet.' }); }, 1200);
    });
    container.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' && (ev.metaKey || ev.ctrlKey) && ev.target.classList && ev.target.classList.contains('ft-th__q')) {
        ev.preventDefault(); var f = ev.target.form; if (f) { if (f.requestSubmit) f.requestSubmit(); else f.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true })); }
      }
    });
    draw();
    return { redraw: draw, thread: thread };
  };
})();
