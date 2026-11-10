/* FundTrail viewer frame: builds the sheet, moves between passages, zooms, and handles the keyboard.
   Renderers (FTViewer.text, .email, .pdf, .photo) draw the document; this file draws everything around it.
   FTViewer.mount(container, file, active)  inline, for design system cards
   FTViewer.open(file, active, opener)      over the app, with a scrim; Esc closes and focus returns to the opener
   Checked quotes (decision 0012): a fact with confirmed:false couldn't be placed in its file. The viewer opens its
   page with no guessed highlight and shows the quote beside it, with two ways to settle it: confirm the value, or
   type the right one. Either marks the fact confirmed by the accountant and still unplaced (placed:false). */
(function () {
  var V = window.FTViewer = window.FTViewer || {};
  V.files = V.files || {};
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function where(file, f) { return file.type === 'pdf' || file.type === 'report' ? 'page ' + f.page : file.type === 'photo' ? '' : 'line ' + f.line; }
  /* A fact is unplaced when its quote couldn't be found (unconfirmed), or when the accountant settled it by hand */
  function unplaced(f) { return f.confirmed === false || f.placed === false; }
  /* Draw the document without the active highlight or box, so nothing is guessed */
  function unmark(html) {
    return html.replace(/<mark class="ft-mark-hl is-active"[^>]*>([\s\S]*?)<\/mark>/g, '$1').replace(/<span class="ft-box ft-photo__box"[^>]*><\/span>/g, '')
      .replace(/<div class="ft-photo__tools">[\s\S]*?<\/div>/, '');
  }

  function Viewer(host, file, active, inline) {
    this.host = host; this.file = file; this.inline = inline;
    this.r = V[file.type];
    this.go(active == null ? (file.active || 0) : active, true);
  }
  Viewer.prototype.html = function () {
    var file = this.file, f = file.facts[this.active], r = this.r, n = file.facts.length, i = this.active, z = this.view.zoom;
    var head = '<header class="ft-sheet__head"><div class="ft-sheet__title"><h2 id="ftv-title">' + esc(file.title) + '</h2>' +
      '<span class="ft-sheet__meta"><span class="ft-id">' + esc(file.name) + '</span> <span class="ft-sep">&middot;</span> ' + String(file.meta || '').split(/\s*·\s*/).map(esc).join(' <span class="ft-sep">&middot;</span> ') + '</span></div>' +
      '<div class="ft-sheet__tools"><button type="button" class="ft-btn ft-btn--sm ft-btn--quiet" data-act="download">Download original</button>' +
      (this.inline ? '' : '<span class="ft-vr" aria-hidden="true"></span><button type="button" class="ft-iconbtn ft-iconbtn--close" data-act="close" aria-label="Close viewer"></button>') + '</div></header>';
    var cite;
    if (f.confirmed === false) cite = '<b>' + esc(f.label) + '</b><span class="ft-vu-flag">Unconfirmed</span><span>' + (file.type === 'photo' ? 'The second look didn’t read the same value' : 'Couldn’t place this quote in the file') + '</span>';
    else if (f.placed === false) cite = '<b>' + esc(f.label) + '</b><span>Confirmed by you <span class="ft-sep">&middot;</span> not placed in the file</span>';
    else cite = r.cite ? r.cite(file, f) : file.type === 'photo'
      ? '<b>' + esc(f.label) + '</b><span>Box checked by a second look</span>'
      : '<b>' + esc(f.label) + '</b><span>Exact passage <span class="ft-sep">&middot;</span> ' + where(file, f) + '</span>';
    var zoom = '';
    if (r.zooms) {
      var lo = z <= r.zooms[0] + 1e-6, hi = z >= r.zooms[r.zooms.length - 1] - 1e-6;
      zoom = '<span class="ft-zoom" role="group" aria-label="Zoom"><button type="button" class="ft-iconbtn ft-iconbtn--minus" data-act="zoomout" aria-label="Zoom out"' + (lo ? ' aria-disabled="true"' : '') + '></button>' +
        '<span class="ft-zoom__level" aria-live="polite">' + Math.round(z * 100) + '%</span><button type="button" class="ft-iconbtn ft-iconbtn--plus" data-act="zoomin" aria-label="Zoom in"' + (hi ? ' aria-disabled="true"' : '') + '></button></span><span class="ft-vr" aria-hidden="true"></span>';
    }
    var pager = '<span class="ft-pager" role="group" aria-label="Passage ' + (i + 1) + ' of ' + n + '"><button type="button" class="ft-iconbtn ft-iconbtn--up" data-act="prev" aria-label="Previous passage"' + (i === 0 ? ' aria-disabled="true"' : '') + '></button>' +
      '<span class="ft-pager__text" aria-hidden="true">' + (i + 1) + ' of ' + n + '</span><button type="button" class="ft-iconbtn ft-iconbtn--down" data-act="next" aria-label="Next passage"' + (i === n - 1 ? ' aria-disabled="true"' : '') + '></button></span>';
    var bar = '<div class="ft-sheet__bar"><div class="ft-sheet__cite" role="status">' + cite + '</div><div class="ft-sheet__controls">' + zoom + pager + '</div></div>';
    var facts = file.facts.map(function (x, k) {
      var loc = where(file, x), mark = '';
      if (x.confirmed === false) mark = '<span class="ft-sidefact__loc ft-vu-side">Unconfirmed</span>';
      else if (x.placed === false) mark = '<span class="ft-sidefact__loc">Confirmed by you</span>';
      else if (loc) mark = '<span class="ft-sidefact__loc">' + loc + '</span>';
      return '<li><button type="button" class="ft-sidefact" data-fact="' + k + '"' + (k === i ? ' aria-current="true"' : '') + '><span class="ft-sidefact__label">' + esc(x.label) + '</span>' +
        '<span class="ft-sidefact__value">' + esc(x.value) + '</span>' + mark + '</button></li>';
    }).join('');
    var side = '<div class="ft-sheet__section"><span class="ft-sheet__label" id="ftv-facts">In this file</span><ul class="ft-sidefacts" aria-labelledby="ftv-facts">' + facts + '</ul></div>';
    if (file.links && file.links.length) side += '<div class="ft-sheet__section"><span class="ft-sheet__label">Linked to</span><ul class="ft-sidelinks">' + file.links.map(function (l) {
      return '<li><span class="ft-id">' + esc(l.id) + '</span><span>' + esc(l.name) + '</span><span class="ft-caption">' + esc(l.amount) + '</span></li>';
    }).join('') + '</ul></div>';
    else if (file.note) side += '<div class="ft-sheet__section"><span class="ft-sheet__label">Status</span><p class="ft-sheet__note" style="margin:0">' + esc(file.note) + '</p></div>';
    var page = this.r.render(file, i, this.view);
    if (unplaced(f)) page = unmark(page);
    var doc = '<div class="ft-sheet__doc" tabindex="0" aria-label="' + esc(file.name) + '">' + this.settleHtml(f) + page + '</div>';
    return head + bar + '<div class="ft-sheet__body">' + doc + '<aside class="ft-sheet__side" aria-label="Facts and links">' + side + '</aside></div>';
  };
  /* The panel beside an unconfirmed fact's page: the quote, why it matters, and the two ways to settle it */
  Viewer.prototype.settleHtml = function (f) {
    var file = this.file;
    if (this.done) return '<div class="ft-vu-wrap"><div class="ft-trail__done ft-vu-done" role="status" tabindex="-1" id="ftv-done"><span>' + esc(this.done) + '</span><button type="button" data-act="vu-undo">Undo</button></div></div>';
    if (f.confirmed !== false) return '';
    var photo = file.type === 'photo', loc = where(file, f);
    var quote = photo
      ? '<p class="ft-vu__quote"><span class="ft-vu__said">The agent read</span> <span class="ft-quote">“' + esc(f.value) + '”</span></p>'
      : '<p class="ft-vu__quote ft-quote">“' + esc(f.text || f.value) + '”' + (loc ? ' <span class="ft-loc">' + loc + ', not found there</span>' : '') + '</p>';
    var form = this.typing
      ? '<form class="ft-inline-edit ft-vu__form" data-vu-form><input class="ft-input" name="v" aria-label="The right value for ' + esc(f.label.toLowerCase()) + '" value="' + esc(f.value) + '"><button class="ft-btn ft-btn--sm">Save</button><button type="button" class="ft-overrule" data-act="vu-cancel">Cancel</button></form>'
      : '<div class="ft-vu__actions"><button type="button" class="ft-btn ft-btn--sm ft-btn--approve" data-act="vu-confirm">Confirm ' + esc(f.value) + '</button><button type="button" class="ft-btn ft-btn--sm" data-act="vu-type">Type the right value</button></div>';
    return '<div class="ft-vu-wrap"><section class="ft-vu" aria-labelledby="ftv-vu-h">' +
      '<div class="ft-vu__head"><span class="ft-vu__mark" aria-hidden="true"></span><b id="ftv-vu-h">' + (photo ? 'The second look didn’t confirm this value' : 'Couldn’t place this quote in the file') + '</b></div>' +
      quote +
      '<p class="ft-vu__why">' + (photo ? 'No box is drawn, so nothing is guessed. ' : 'No highlight is drawn, so nothing is guessed. ') + 'Anything that rests on this fact is in Needs a human until you confirm the value or type the right one.</p>' +
      form + '</section></div>';
  };
  /* Settle an unconfirmed fact by hand; Undo puts it back as it was */
  Viewer.prototype.settle = function (value) {
    var f = this.file.facts[this.active];
    this.undo = { i: this.active, value: f.value, confirmed: f.confirmed, placed: f.placed, by: f.confirmedBy };
    var typed = value != null && value !== f.value;
    if (value != null) f.value = value;
    f.confirmed = true; f.placed = false; f.confirmedBy = 'you'; this.typing = false;
    this.done = (typed ? 'Set by you: ' + f.value + '.' : 'Confirmed by you: ' + f.value + '.') + ' Anything that rested on it rechecks.';
    this.draw(true, '#ftv-done');
  };
  Viewer.prototype.unsettle = function () {
    var u = this.undo; if (!u) return;
    var f = this.file.facts[u.i];
    f.value = u.value; f.confirmed = u.confirmed; f.placed = u.placed; f.confirmedBy = u.by;
    this.undo = null; this.done = null;
    this.draw(true, '[data-act="vu-confirm"]');
  };
  Viewer.prototype.draw = function (smooth, focusSel) {
    var a = document.activeElement, key = null;
    if (a && this.host.contains(a)) key = a.getAttribute('data-act') ? '[data-act="' + a.getAttribute('data-act') + '"]' : a.getAttribute('data-fact') ? '[data-fact="' + a.getAttribute('data-fact') + '"]' : a.classList.contains('ft-sheet__doc') ? '.ft-sheet__doc' : null;
    var doc0 = this.host.querySelector('.ft-sheet__doc'), keepTop = doc0 ? doc0.scrollTop : 0, keepLeft = doc0 ? doc0.scrollLeft : 0;
    this.host.innerHTML = this.html();
    var doc = this.host.querySelector('.ft-sheet__doc');
    if (smooth) doc.scrollTo({ top: keepTop, left: keepLeft, behavior: 'instant' });
    /* Renderers that fit to the window (the whole photo) know their real zoom only once drawn */
    var lv = this.host.querySelector('.ft-zoom__level'), zi = this.host.querySelector('[data-act="zoomin"]'), zo = this.host.querySelector('[data-act="zoomout"]');
    if (lv && this.r.levelText) lv.textContent = this.r.levelText(this.view, doc);
    if (zi && this.r.canStep) { zi.setAttribute('aria-disabled', String(!this.r.canStep(this.view, 1, doc))); zo.setAttribute('aria-disabled', String(!this.r.canStep(this.view, -1, doc))); }
    var t = focusSel ? this.host.querySelector(focusSel) : key ? this.host.querySelector(key) : null;
    if (t) t.focus({ preventScroll: true });
    this.reveal(smooth);
    var side = this.host.querySelector('.ft-sheet__side'), sf = side && side.querySelector('[aria-current="true"]');
    if (sf) { var s = side.getBoundingClientRect(), r = sf.getBoundingClientRect(); if (r.top < s.top || r.bottom > s.bottom) side.scrollTop += r.top - s.top - (side.clientHeight - r.height) / 2; }
  };
  Viewer.prototype.reveal = function (smooth, settled) {
    var doc = this.host.querySelector('.ft-sheet__doc'), f = this.file.facts[this.active], el;
    if (doc && unplaced(f)) {
      /* Nothing to point at: open the fact's page when it has one, else the top, with the panel in view */
      var pages = doc.querySelectorAll('.ft-pdf__sheet, .ft-rpage');
      el = f.page && pages[f.page - 1] && f.page > 1 ? pages[f.page - 1] : null;
      if (!el) { doc.scrollTo({ top: 0, left: 0, behavior: 'instant' }); return; }
    } else el = doc && this.r.target(doc, this.file, this.active);
    if (!el) return;
    if (settled) smooth = false;
    var d = doc.getBoundingClientRect(), e = el.getBoundingClientRect();
    var top = doc.scrollTop + (e.top - d.top) - (e.height > doc.clientHeight - 32 ? 16 : (doc.clientHeight - e.height) / 2);
    var left = doc.scrollLeft + (e.left - d.left) - (doc.clientWidth - e.width) / 2;
    doc.scrollTo({ top: Math.max(0, top), left: Math.max(0, left), behavior: smooth && !reduce ? 'smooth' : 'instant' });
    if (!smooth && !settled && document.fonts && document.fonts.ready) { var self = this, i = this.active; document.fonts.ready.then(function () { if (self.active === i && self.host.isConnected) self.reveal(false, true); }); }
  };
  Viewer.prototype.go = function (i, first, focusSel) {
    var n = this.file.facts.length; i = Math.max(0, Math.min(n - 1, i));
    var keepZoom = this.view && this.file.type === 'pdf';
    if (i !== this.active) { this.typing = false; this.done = null; this.undo = null; }
    this.active = i;
    if (!keepZoom) this.view = this.r.initialView ? this.r.initialView(this.file, i) : { zoom: 1, whole: false };
    /* A photo fact that isn't placed has no box to zoom to: show the whole photo */
    if (this.file.type === 'photo' && unplaced(this.file.facts[i])) this.view.whole = true;
    this.draw(!first, focusSel);
  };
  Viewer.prototype.zoom = function (dir) {
    var zs = this.r.zooms; if (!zs) return;
    if (this.r.step) { this.view = this.r.step(this.view, dir, this.host.querySelector('.ft-sheet__doc')); this.draw(true, dir > 0 ? '[data-act="zoomin"]' : '[data-act="zoomout"]'); return; }
    var z = this.view.zoom, k;
    if (dir > 0) { for (k = 0; k < zs.length && zs[k] <= z + 1e-6; k++); this.view.zoom = zs[Math.min(k, zs.length - 1)]; }
    else { for (k = zs.length - 1; k >= 0 && zs[k] >= z - 1e-6; k--); this.view.zoom = zs[Math.max(k, 0)]; }
    this.view.whole = false;
    this.draw(true);
  };
  Viewer.prototype.handle = function (e) {
    var t = e.target.closest ? e.target.closest('[data-act], [data-fact]') : null;
    if (!t || !this.host.contains(t)) return;
    if (t.getAttribute('aria-disabled') === 'true') return;
    var act = t.getAttribute('data-act'), f = t.getAttribute('data-fact');
    if (f != null) return this.go(parseInt(f, 10), false, '[data-fact="' + f + '"]');
    if (act === 'prev') this.go(this.active - 1);
    else if (act === 'next') this.go(this.active + 1);
    else if (act === 'zoomin') this.zoom(1);
    else if (act === 'zoomout') this.zoom(-1);
    else if (act === 'whole') { this.view.whole = !this.view.whole; this.draw(true, '[data-act="whole"]'); }
    else if (act === 'close') V.close();
    else if (act === 'vu-confirm') this.settle(null);
    else if (act === 'vu-type') { this.typing = true; this.draw(true, '[data-vu-form] input'); var inp = this.host.querySelector('[data-vu-form] input'); if (inp) inp.select(); }
    else if (act === 'vu-cancel') { this.typing = false; this.draw(true, '[data-act="vu-type"]'); }
    else if (act === 'vu-undo') this.unsettle();
  };
  Viewer.prototype.submit = function (e) {
    var form = e.target; if (!form.hasAttribute || !form.hasAttribute('data-vu-form')) return;
    e.preventDefault();
    var v = form.elements.v.value.trim(); if (!v) { form.elements.v.focus(); return; }
    this.settle(v);
  };
  Viewer.prototype.key = function (e) {
    var f = e.target.getAttribute && e.target.getAttribute('data-fact');
    if (f != null && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) { e.preventDefault(); var k = parseInt(f, 10) + (e.key === 'ArrowDown' ? 1 : -1); if (k >= 0 && k < this.file.facts.length) this.go(k, false, '[data-fact="' + k + '"]'); }
  };
  function wire(v) {
    v.host.addEventListener('click', function (e) { v.handle(e); });
    v.host.addEventListener('keydown', function (e) { v.key(e); });
    v.host.addEventListener('submit', function (e) { v.submit(e); });
  }

  V.mount = function (container, file, active) {
    container.classList.add('ft-sheet', 'ft-sheet--inline');
    container.setAttribute('aria-labelledby', 'ftv-title');
    var v = new Viewer(container, file, active, true); wire(v); return v;
  };

  var cur = null;
  V.open = function (file, active, opener) {
    if (cur) V.close(true);
    var scrim = document.createElement('div'); scrim.className = 'ft-scrim' + (reduce ? '' : ' ft-scrim--in');
    var sheet = document.createElement('section');
    sheet.className = 'ft-sheet' + (reduce ? '' : ' ft-sheet--in');
    sheet.setAttribute('role', 'dialog'); sheet.setAttribute('aria-modal', 'true'); sheet.setAttribute('aria-labelledby', 'ftv-title'); sheet.tabIndex = -1;
    var app = document.querySelector('.ft-app'); if (app) app.setAttribute('inert', '');
    document.body.appendChild(scrim); document.body.appendChild(sheet);
    var v = new Viewer(sheet, file, active, false); wire(v);
    scrim.addEventListener('click', function () { V.close(); });
    sheet.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { e.preventDefault(); V.close(); return; }
      if (e.key !== 'Tab') return;
      var els = Array.prototype.filter.call(sheet.querySelectorAll('button:not([disabled]), input, [tabindex="0"]'), function (x) { return x.offsetParent !== null; });
      if (!els.length) return;
      var first = els[0], last = els[els.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === sheet)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });
    cur = { v: v, scrim: scrim, sheet: sheet, opener: opener, app: app };
    sheet.focus({ preventScroll: true });
    v.reveal(false);
    return v;
  };
  V.close = function (silent) {
    if (!cur) return;
    var c = cur; cur = null;
    if (c.app) c.app.removeAttribute('inert');
    c.scrim.remove(); c.sheet.remove();
    if (!silent && c.opener && c.opener.isConnected) c.opener.focus();
    if (V.onclose) V.onclose();
  };
  V.isOpen = function () { return !!cur; };
})();
