/* FundTrail problem list: records with problems of their own, the row actions (Snooze, Accept with a note),
   the two dialogs, and the standing notes list. Follows PR 6 (decision 0010), not merged yet.

   FTProblems.recordRowHtml(rec, opts)   a record row that sits in the same .ft-ledger list as charge rows
     rec: { id, kind: 'term'|'unlinked'|'overlinked'|'disagree'|'duplicate'|'flag', title, why, listed (date text),
            by: 'code'|'agent', amount? (text), actions? (array of act ids; default per kind), selected? }
   FTProblems.rowActionsHtml(id, acts)   the quiet row actions for a charge row: put it inside .ft-row__desc
     acts default ['snooze', 'accept']; other ids: 'confirm-dup', 'not-dup', 'open'
   FTProblems.bind(container, handlers)  delegated clicks on [data-pb-act]: handlers[act](id, button); stops the row's own click
   FTProblems.acceptDialog(opts, onDone) opts: { target: {id, title, problem, account?, vendor?, amount?, kind: 'charge'|'record'},
                                                 opener, alsoCovers? (number of other charges a standing note would cover today) }
                                          onDone({ note, standing }) ; returns nothing. Esc, Cancel and the scrim close it.
   FTProblems.snoozeDialog(opts, onDone) opts: { target, opener, today: 'YYYY-MM-DD', windowOpens: 'YYYY-MM-DD' }
                                          onDone({ until: 'YYYY-MM-DD', untilText, reason })
   FTProblems.acceptDialogHtml / snoozeDialogHtml(opts)   the same markup, for static cards
   FTProblems.doneText(kind, target, result)   the sentence for the inline done line (ft-trail__done) after an action
   FTProblems.stateTagHtml(state)        { state: 'snoozed'|'accepted'|'standing', until? } for a charge that left the list
   FTProblems.standingNotesHtml(notes, opts)  notes: [{ id, note, by, date, problem, account, vendor, covers: [{id, name, amount}] }]
   FTProblems.fmtDate('YYYY-MM-DD') -> 'Apr 30, 2026' */
(function () {
  var P = window.FTProblems = window.FTProblems || {};
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function parse(iso) { var p = String(iso).split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function iso(d) { function z(n) { return (n < 10 ? '0' : '') + n; } return d.getFullYear() + '-' + z(d.getMonth() + 1) + '-' + z(d.getDate()); }
  P.fmtDate = function (s) { var d = parse(s); return MONTHS[d.getMonth()] + ' ' + d.getDate() + ', ' + d.getFullYear(); };

  /* What each kind of record is called, and what you can do about it on the row */
  var KINDS = {
    term: { tag: 'Term to confirm', acts: ['open', 'snooze'] },
    unlinked: { tag: 'Bill not charged', acts: ['snooze', 'accept'] },
    overlinked: { tag: 'Bill over-linked', acts: ['open', 'snooze'] },
    disagree: { tag: 'Terms disagree', acts: ['open', 'snooze'] },
    duplicate: { tag: 'Duplicate file', acts: ['confirm-dup', 'not-dup'] },
    flag: { tag: 'Agent flag', acts: ['snooze', 'accept'] }
  };
  var ACT_LABEL = { snooze: 'Snooze', accept: 'Accept with a note', open: 'Review', 'confirm-dup': 'Confirm duplicate', 'not-dup': 'Not a duplicate' };
  P.KINDS = KINDS;

  P.rowActionsHtml = function (id, acts, name) {
    acts = acts || ['snooze', 'accept'];
    return '<span class="ft-pb-actions" role="group" aria-label="Actions for ' + esc(name || id) + '">' + acts.map(function (a) {
      return '<button type="button" class="ft-pb-act" data-pb-act="' + a + '" data-pb-id="' + esc(id) + '">' + ACT_LABEL[a] + '</button>';
    }).join('') + '</span>';
  };

  P.recordRowHtml = function (rec, opts) {
    opts = opts || {};
    var k = KINDS[rec.kind] || KINDS.flag;
    var by = rec.by === 'agent' ? 'Flagged by the agent' : 'Raised by code';
    return '<div class="ft-row ft-pb-row ft-pb-row--' + rec.kind + (rec.selected ? ' is-selected' : '') + '" role="row" tabindex="0" data-id="' + esc(rec.id) + '" data-row="record">' +
      '<span class="ft-row__date">' + esc(rec.listed) + '<span class="ft-id ft-pb-rec">Record</span></span>' +
      '<span class="ft-row__desc"><span class="ft-row__name">' + esc(rec.title) + '</span>' +
        '<span class="ft-row__reason">' + esc(rec.why) + ' <span class="ft-pb-by">' + by + '.</span></span>' +
        (opts.actions === false ? '' : P.rowActionsHtml(rec.id, rec.actions || k.acts, rec.title)) + '</span>' +
      '<span class="ft-row__amount ft-amount">' + esc(rec.amount || '') + '</span>' +
      '<span class="ft-row__bucket"><span class="ft-pb-kind">' + k.tag + '</span></span></div>';
  };

  P.bind = function (container, handlers) {
    container.addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('[data-pb-act]') : null;
      if (!b || !container.contains(b)) return;
      /* stopImmediatePropagation: a row-select listener on the same list would redraw it and drop the button the dialog returns focus to */
      e.stopImmediatePropagation(); e.stopPropagation(); e.preventDefault();
      var f = handlers && handlers[b.getAttribute('data-pb-act')];
      if (f) f(b.getAttribute('data-pb-id'), b);
    });
    container.addEventListener('keydown', function (e) {
      if (e.target.closest && e.target.closest('[data-pb-act]') && (e.key === 'Enter' || e.key === ' ')) e.stopPropagation();
    });
  };

  P.stateTagHtml = function (s) {
    var t = s.state === 'snoozed' ? 'Snoozed until ' + P.fmtDate(s.until) : s.state === 'standing' ? 'Accepted under the accountant’s note' : 'Accepted with your note';
    return '<span class="ft-pb-state ft-pb-state--' + s.state + '">' + esc(t) + '</span>';
  };

  P.doneText = function (kind, target, r) {
    var who = target.id && target.kind !== 'record' ? target.id : target.title;
    if (kind === 'snooze') return who + ' snoozed until ' + r.untilText + '. It comes back then if it isn’t fixed.';
    if (r.standing) return who + ' accepted with a standing note. It also covers every charge with the same problem, account and vendor.';
    return who + ' accepted with your note. It leaves the problem list, and comes back if the facts change.';
  };

  /* ---------- the dialogs ---------- */
  var seq = 0;
  function summary(t) {
    return '<div class="ft-pb-target"><span class="ft-pb-target__name">' + (t.kind === 'record' ? '' : '<span class="ft-id">' + esc(t.id) + '</span> ') + esc(t.title) +
      (t.amount ? ' <span class="ft-sep">&middot;</span> <span class="ft-amount">' + esc(t.amount) + '</span>' : '') + '</span>' +
      '<span class="ft-pb-target__problem">' + esc(t.problem) + '</span></div>';
  }
  P.acceptDialogHtml = function (o, id) {
    id = id || 'ft-pb-' + (++seq);
    var t = o.target, charge = t.kind !== 'record', canStand = charge && !!t.vendor;
    var stand = '';
    if (charge) {
      stand = '<div class="ft-pb-standing' + (canStand ? '' : ' is-off') + '">' +
        '<label class="ft-pb-check"><input type="checkbox" name="standing"' + (canStand ? '' : ' disabled') + (o.standing && canStand ? ' checked' : '') + ' aria-describedby="' + id + '-st"> Make it a standing note</label>' +
        '<p id="' + id + '-st">' + (canStand
          ? 'It also covers every charge on this grant, past and future, with this same problem, ledger account and vendor. Every other check still runs.'
          : 'This charge has no vendor, so the note can only cover this charge.') + '</p>' +
        (canStand ? '<dl class="ft-pb-covers"><dt>Problem</dt><dd>' + esc(t.problemShort || t.problem) + '</dd><dt>Account</dt><dd>' + esc(t.account) + '</dd><dt>Vendor</dt><dd>' + esc(t.vendor) + '</dd>' +
          '<dt>Today</dt><dd>This charge' + (o.alsoCovers ? ' and ' + o.alsoCovers + ' other' + (o.alsoCovers > 1 ? 's' : '') : ' only. Later charges that match are covered as they arrive.') + '</dd></dl>' : '') +
        '</div>';
    }
    return '<form class="ft-dialog-form" novalidate data-pb-form="accept"><div class="ft-dialog-head"><h2 class="ft-dialog-title" id="' + id + '-t">Accept with a note</h2></div>' +
      '<div class="ft-dialog-body"><p id="' + id + '-d" class="ft-pb-lede">It will never fix itself, and you’re fine with it. It leaves the problem list, and comes back if the facts change.</p>' + summary(t) +
      '<div class="ft-field" id="' + id + '-field"><label class="ft-field__label" for="' + id + '-note">Note</label>' +
      '<textarea class="ft-textarea" id="' + id + '-note" name="note" rows="3" aria-required="true" aria-describedby="' + id + '-help" placeholder="For example: moving it off the grant in the adjustment period.">' + esc(o.note || '') + '</textarea>' +
      '<span class="ft-field__hint" id="' + id + '-help">Goes into the evidence report under your name.</span></div>' + stand + '</div>' +
      '<div class="ft-dialog-foot"><button type="button" class="ft-btn" data-pb-dialog="cancel">Cancel</button><button type="submit" class="ft-btn ft-btn--main">Accept with a note</button></div></form>';
  };
  P.snoozeDialogHtml = function (o, id) {
    id = id || 'ft-pb-' + (++seq);
    var t = o.target, today = o.today || iso(new Date()), win = o.windowOpens;
    var min = iso(new Date(parse(today).getTime() + 86400000));
    var def = o.until || iso(new Date(parse(today).getTime() + 14 * 86400000));
    if (win && def > win) def = win;
    return '<form class="ft-dialog-form" novalidate data-pb-form="snooze"><div class="ft-dialog-head"><h2 class="ft-dialog-title" id="' + id + '-t">Snooze until a date</h2></div>' +
      '<div class="ft-dialog-body"><p id="' + id + '-d" class="ft-pb-lede">You expect it to fix itself. It comes back on that date if it isn’t fixed, or sooner if a new problem shows up.</p>' + summary(t) +
      '<div class="ft-pb-grid"><div class="ft-field" id="' + id + '-dfield"><label class="ft-field__label" for="' + id + '-date">Bring it back on</label>' +
      '<input class="ft-input" type="date" id="' + id + '-date" name="until" value="' + def + '" min="' + min + '"' + (win ? ' max="' + win + '"' : '') + ' aria-describedby="' + id + '-dhelp">' +
      '<span class="ft-field__hint" id="' + id + '-dhelp">' + (win ? 'Every snooze ends ' + P.fmtDate(win) + ', when the 90-day closeout window opens.' : 'Every snooze ends when the 90-day closeout window opens.') + '</span></div>' +
      '<div class="ft-field" id="' + id + '-rfield"><label class="ft-field__label" for="' + id + '-reason">Why</label>' +
      '<input class="ft-input" id="' + id + '-reason" name="reason" autocomplete="off" aria-required="true" aria-describedby="' + id + '-rhelp" placeholder="For example: refund coming, check Mar 1" value="' + esc(o.reason || '') + '">' +
      '<span class="ft-field__hint" id="' + id + '-rhelp">Shows on the charge while it’s snoozed.</span></div></div></div>' +
      '<div class="ft-dialog-foot"><button type="button" class="ft-btn" data-pb-dialog="cancel">Cancel</button><button type="submit" class="ft-btn ft-btn--main">Snooze</button></div></form>';
  };

  var cur = null;
  function close(returnFocus) {
    if (!cur) return;
    var c = cur; cur = null;
    c.dlg.parentNode.removeChild(c.dlg); c.scrim.parentNode.removeChild(c.scrim);
    var app = document.querySelector('.ft-app');
    if (app && !(window.FTViewer && window.FTViewer.isOpen && window.FTViewer.isOpen())) app.removeAttribute('inert');
    if (returnFocus && c.opener && c.opener.isConnected) c.opener.focus();
  }
  P.close = function () { close(true); };
  function setError(dlg, fieldId, helpId, msg, hint) {
    var f = dlg.querySelector('#' + fieldId), h = dlg.querySelector('#' + helpId), inp = f && f.querySelector('input, textarea');
    if (!f) return;
    f.classList.toggle('is-invalid', !!msg);
    if (msg) { inp.setAttribute('aria-invalid', 'true'); h.className = 'ft-field__error'; h.textContent = msg; }
    else { inp.removeAttribute('aria-invalid'); h.className = 'ft-field__hint'; h.textContent = hint; }
  }
  function open(kind, o, onDone) {
    close(false);
    var id = 'ft-pb-' + (++seq);
    var scrim = document.createElement('div'); scrim.className = 'ft-scrim' + (reduce ? '' : ' ft-scrim--in');
    var dlg = document.createElement('section');
    dlg.className = 'ft-dialog ft-pb-dialog' + (reduce ? '' : ' ft-dialog--in');
    dlg.setAttribute('role', 'dialog'); dlg.setAttribute('aria-modal', 'true');
    dlg.setAttribute('aria-labelledby', id + '-t'); dlg.setAttribute('aria-describedby', id + '-d'); dlg.tabIndex = -1;
    dlg.innerHTML = kind === 'accept' ? P.acceptDialogHtml(o, id) : P.snoozeDialogHtml(o, id);
    var app = document.querySelector('.ft-app'); if (app) app.setAttribute('inert', '');
    document.body.appendChild(scrim); document.body.appendChild(dlg);
    cur = { dlg: dlg, scrim: scrim, opener: o.opener || document.activeElement };
    scrim.addEventListener('click', function () { close(true); });
    dlg.addEventListener('click', function (e) { var b = e.target.closest ? e.target.closest('[data-pb-dialog="cancel"]') : null; if (b) close(true); });
    dlg.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(true); return; }
      if (e.key !== 'Tab') return;
      var els = Array.prototype.filter.call(dlg.querySelectorAll('button:not([disabled]), input:not([disabled]), textarea'), function (x) { return x.offsetParent !== null; });
      if (!els.length) return;
      var first = els[0], last = els[els.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === dlg)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });
    var form = dlg.querySelector('form');
    if (kind === 'accept') {
      var note = form.elements.note, noteHint = 'Goes into the evidence report under your name.';
      note.addEventListener('input', function () { if (note.value.trim()) setError(dlg, id + '-field', id + '-help', null, noteHint); });
      form.addEventListener('submit', function (e) {
        e.preventDefault(); e.stopPropagation();
        var v = note.value.replace(/\s+/g, ' ').trim();
        if (!v) { setError(dlg, id + '-field', id + '-help', 'Add a note. It goes into the evidence report.', noteHint); note.focus(); return; }
        var st = form.elements.standing ? form.elements.standing.checked : false;
        close(true); if (onDone) onDone({ note: v, standing: st });
      });
      note.focus();
    } else {
      var d = form.elements.until, r = form.elements.reason, win = o.windowOpens, today = o.today || iso(new Date());
      var dHint = win ? 'Every snooze ends ' + P.fmtDate(win) + ', when the 90-day closeout window opens.' : 'Every snooze ends when the 90-day closeout window opens.';
      var rHint = 'Shows on the charge while it’s snoozed.';
      d.addEventListener('input', function () { setError(dlg, id + '-dfield', id + '-dhelp', null, dHint); });
      r.addEventListener('input', function () { if (r.value.trim()) setError(dlg, id + '-rfield', id + '-rhelp', null, rHint); });
      form.addEventListener('submit', function (e) {
        e.preventDefault(); e.stopPropagation();
        var until = d.value, why = r.value.replace(/\s+/g, ' ').trim(), bad = false;
        if (!until || until <= today) { setError(dlg, id + '-dfield', id + '-dhelp', 'Pick a date after ' + P.fmtDate(today) + '.', dHint); bad = d; }
        else if (win && until > win) { setError(dlg, id + '-dfield', id + '-dhelp', 'Pick a date by ' + P.fmtDate(win) + '. The closeout window ends every snooze.', dHint); bad = d; }
        if (!why) { setError(dlg, id + '-rfield', id + '-rhelp', 'Say why you expect it to fix itself.', rHint); bad = bad || r; }
        if (bad) { bad.focus(); return; }
        close(true); if (onDone) onDone({ until: until, untilText: P.fmtDate(until), reason: why });
      });
      r.focus();
    }
  }
  P.acceptDialog = function (o, onDone) { open('accept', o, onDone); };
  P.snoozeDialog = function (o, onDone) { open('snooze', o, onDone); };
  P.isOpen = function () { return !!cur; };

  /* ---------- standing notes ---------- */
  P.standingNotesHtml = function (notes, opts) {
    opts = opts || {};
    var head = '<div class="ft-pb-notes__head"><h3 class="ft-heading" id="ft-pb-notes-h">Standing notes</h3>' +
      '<span class="ft-caption">Each covers every charge with the same problem, account and vendor. Every other check still runs.</span></div>';
    if (!notes || !notes.length) return '<section class="ft-pb-notes" aria-labelledby="ft-pb-notes-h">' + head +
      '<p class="ft-pb-notes__empty">No standing notes. When you accept a problem with a note, you can make it cover every charge like it.</p></section>';
    return '<section class="ft-pb-notes" aria-labelledby="ft-pb-notes-h">' + head + '<ul class="ft-pb-notes__list">' + notes.map(function (n) {
      return '<li class="ft-pb-note"><div class="ft-pb-note__main"><p class="ft-pb-note__text">“' + esc(n.note) + '”</p>' +
        '<dl class="ft-pb-covers"><dt>Problem</dt><dd>' + esc(n.problem) + '</dd><dt>Account</dt><dd>' + esc(n.account) + '</dd><dt>Vendor</dt><dd>' + esc(n.vendor) + '</dd></dl>' +
        '<span class="ft-caption">Written by ' + esc(n.by) + ', ' + esc(n.date) + '</span></div>' +
        '<div class="ft-pb-note__covers"><span class="ft-pb-note__label">Covers ' + n.covers.length + ' charge' + (n.covers.length === 1 ? '' : 's') + '</span><ul>' +
        n.covers.map(function (c) { return '<li><span class="ft-id">' + esc(c.id) + '</span><span>' + esc(c.name) + '</span><span class="ft-amount">' + esc(c.amount) + '</span></li>'; }).join('') + '</ul>' +
        '<button type="button" class="ft-pb-act ft-pb-act--withdraw" data-pb-act="withdraw" data-pb-id="' + esc(n.id) + '">Withdraw note</button>' +
        '<span class="ft-caption">Withdrawing brings these charges back to the problem list.</span></div></li>';
    }).join('') + '</ul></section>';
  };
})();
