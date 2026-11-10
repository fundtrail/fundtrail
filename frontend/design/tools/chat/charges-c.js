/* Chat option C on the Charges page: the grant header and budget band stay put; under them the charge list
   and the selected charge fill the rest of the screen and scroll on their own. The charge's details scroll
   in the panel, and its review thread is docked at the bottom of the panel, always on screen, with the ask
   box pinned last. One conversation: the dock holds the charge's own thread section, moved there after each
   redraw. Same proportions, Show more and transition as the Demo's option C (chat-c.js). */
(function () {
  var css = '' +
    '.ft-app { min-height: 0 !important; height: 100vh; }' +
    '.ft-sidebar { position: sticky !important; top: 0; height: 100vh !important; overflow-y: auto; }' +
    '.ft-main { height: 100vh; min-height: 0; overflow: hidden; }' +
    '.ft-content { flex: 1; min-height: 0; overflow: hidden; }' +
    '.ft-content > .ft-ch-split { flex: 1; min-height: 0; align-items: stretch; grid-template-rows: minmax(0, 1fr); }' +
    '.ft-ch-split > .ft-panel:first-child { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }' +
    '.ft-ch-split > .ft-panel:first-child > :not(.ft-ch-scroll) { flex: none; }' +
    '.ft-ch-split > .ft-panel:first-child > .ft-ch-scroll { flex: 1 1 auto; min-height: 0; max-height: none !important; }' +
    '#ch-detail.ft-cc { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }' +
    '.ft-cc-scroll { flex: 1 1 auto; min-height: 0; overflow-y: auto; overscroll-behavior: contain; }' +
    '.ft-cc-dock { flex: none; display: flex; flex-direction: column; min-height: 0; height: var(--ft-cc-dock, 42%); border-top: 1px solid var(--rule-strong); background: var(--paper-raised); }' +
    '.ft-cc-dockbar { flex: none; display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 6px var(--space-4) 0; }' +
    '.ft-cc-dockbar span { font-size: 12px; line-height: 16px; font-weight: 600; color: var(--ink-muted); }' +
    '.ft-cc-grow { font: inherit; font-size: 12px; font-weight: 600; color: var(--ink); background: none; border: 0; padding: 4px 0; cursor: pointer; text-decoration: underline; text-decoration-color: var(--rule-strong); text-underline-offset: 3px; }' +
    '.ft-cc-grow:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }' +
    '.ft-cc-dock > .ft-panel__section { flex: 1; min-height: 0; display: flex; flex-direction: column; padding-top: 4px !important; padding-bottom: var(--space-3) !important; }' +
    '.ft-cc-dock #ch-th, .ft-cc-dock .ft-th { flex: 1; min-height: 0; display: flex; flex-direction: column; }' +
    '.ft-cc-dock .ft-th__head { display: none; }' +
    '.ft-cc-dock .ft-th__list { flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain; }' +
    '.ft-cc-dock .ft-th__ask { flex: none; }' + '.ft-cc-dock .ft-th__note { font-size: 11px; line-height: 15px; }' +
    '.ft-toast { left: calc(var(--sidebar-width) + 24px) !important; transform: none !important; }' +
    '@media (prefers-reduced-motion: no-preference) { .ft-cc-in { animation: ft-cc-in 160ms ease both; } }' +
    '@keyframes ft-cc-in { from { opacity: 0; transform: translateX(10px); } to { opacity: 1; transform: none; } }' +
    '@media (max-width: 1023px) { .ft-app, .ft-main, .ft-content { height: auto; overflow: visible; } .ft-ch-split > .ft-panel:first-child, .ft-cc-scroll { overflow: visible; } .ft-ch-split > .ft-panel:first-child > .ft-ch-scroll { max-height: max(360px, calc(100vh - 470px)) !important; } #ch-detail.ft-cc { overflow: visible; } .ft-cc-dock { height: auto; } }';
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  /* The dock is its own part: a tinted surface, a firm top edge, and a header naming what the thread is about.
     While there is more of the charge above it, the details fade out and the dock casts a soft edge. */
  var dockCss = [
    '.ft-cc-dock { position: relative; background: color-mix(in srgb, var(--paper-sunken) 70%, var(--paper-raised)); border-top: 1px solid var(--rule-strong); }',
    '.ft-cc-dockbar { padding: 10px var(--space-4) 8px; border-bottom: 1px solid var(--rule); }',
    '.ft-cc-dockhead { display: flex; align-items: baseline; gap: 8px; min-width: 0; }',
    '.ft-cc-dockbar .ft-cc-title { font-size: 13px; line-height: 18px; font-weight: 600; color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }',
    '.ft-cc-dockbar .ft-cc-title .ft-id { font-size: 12px; color: var(--ink); }',
    '.ft-cc-dockbar .ft-cc-title .ft-sep { color: var(--ink-muted); font-weight: 400; }',
    '.ft-cc-dockbar .ft-cc-count { font-size: 12px; line-height: 16px; font-weight: 400; color: var(--ink-muted); white-space: nowrap; }',
    '.ft-cc-dockbar .ft-cc-count b { font-weight: 600; }',
    '.ft-cc-dock > .ft-panel__section { padding-top: 8px !important; }',
    '.ft-cc-dock .ft-th__ask { border-top: 1px solid var(--rule); padding-top: 10px; margin-top: 4px; }',
    '.ft-cc-dock::before { content: ""; position: absolute; left: 0; right: 0; bottom: 100%; height: 28px; margin-bottom: 1px; pointer-events: none; opacity: 0; background: linear-gradient(to bottom, color-mix(in srgb, var(--paper-raised) 0%, transparent), var(--paper-raised)); }',
    '.ft-cc--more .ft-cc-dock { box-shadow: 0 -10px 16px -14px rgba(16, 18, 22, 0.32); }',
    '[data-theme="dark"] .ft-cc--more .ft-cc-dock { box-shadow: 0 -10px 16px -12px rgba(0, 0, 0, 0.7); }',
    '.ft-cc--more .ft-cc-dock::before { opacity: 1; }',
    '@media (prefers-reduced-motion: no-preference) { .ft-cc-dock::before { transition: opacity 160ms ease; } .ft-cc-dock { transition: box-shadow 160ms ease; } }',
    '@media (max-width: 1023px) { .ft-cc-dock::before { display: none; } .ft-cc--more .ft-cc-dock { box-shadow: none; } }'
  ].join('\n');
  var st2 = document.createElement('style'); st2.textContent = dockCss; document.head.appendChild(st2);

  /* The dock's header: what the thread is about (the charge's ledger line, or a record's name) and its count */
  function label(det, dock) {
    var t = dock && dock.querySelector('.ft-cc-title'), c = dock && dock.querySelector('.ft-cc-count'); if (!t) return;
    var idEl = det.querySelector('.ft-cc-scroll .ft-id'), id = idEl ? idEl.textContent.trim() : '';
    if (!/^L-\d+/.test(id)) { var h = det.querySelector('.ft-cc-scroll .ft-charge-title, .ft-cc-scroll h2'); id = h ? h.textContent.trim().split(',')[0] : ''; }
    var about = /^L-\d+/.test(id) ? '<span class="ft-id">' + id + '</span>' : id.replace(/[&<>"]/g, '');
    t.innerHTML = 'Agent thread' + (about ? ' <span class="ft-sep">&middot;</span> ' + about : '');
    var src = dock.querySelector('.ft-th__count'); if (c) c.innerHTML = src ? src.innerHTML : '';
  }
  /* The scroll cue is on while the details have more below what's visible */
  function cue(det) {
    var s = det && det.querySelector(':scope > .ft-cc-scroll'); if (!s) return;
    det.classList.toggle('ft-cc--more', s.scrollHeight - s.scrollTop - s.clientHeight > 4);
  }

  var tall = false, last = null, busy = false;
  function key(det) { var t = det.querySelector('.ft-charge-title, h2'); return t ? t.textContent : ''; }
  function toEnd(dock) { var l = dock && dock.querySelector('.ft-th__list'); if (l) l.scrollTop = l.scrollHeight; }

  function arrange() {
    var det = document.getElementById('ch-detail'); if (!det || busy) return;
    if (det.firstElementChild && det.firstElementChild.classList.contains('ft-cc-scroll') && (det.querySelector('.ft-cc-dock #ch-th') || !det.querySelector('#ch-th'))) return;
    busy = true;
    var focused = document.activeElement, prevScroll = 0, k = key(det);
    var old = det.querySelector(':scope > .ft-cc-scroll'); if (old) prevScroll = old.scrollTop;
    det.classList.add('ft-cc');
    var host = document.getElementById('ch-th'), section = null;
    if (host) { section = host; while (section.parentElement && section.parentElement !== det) section = section.parentElement; if (section.parentElement !== det) section = null; }
    var scroll = document.createElement('div'); scroll.className = 'ft-cc-scroll';
    Array.prototype.slice.call(det.childNodes).forEach(function (n) { if (n !== section) scroll.appendChild(n); });
    det.appendChild(scroll);
    if (section) {
      var dock = document.createElement('div'); dock.className = 'ft-cc-dock';
      dock.innerHTML = '<div class="ft-cc-dockbar"><div class="ft-cc-dockhead"><span class="ft-cc-title">Agent thread</span><span class="ft-cc-count"></span></div><button type="button" class="ft-cc-grow" aria-expanded="' + tall + '">' + (tall ? 'Show less' : 'Show more') + '</button></div>';
      dock.appendChild(section); det.appendChild(dock); label(det, dock);
      size(dock);
      toEnd(dock);
      setTimeout(function () { size(dock); }, 60);
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { size(dock); });
      new MutationObserver(function () { size(dock); toEnd(dock); label(det, dock); cue(det); }).observe(section, { childList: true, subtree: true });
    }
    if (k === last) scroll.scrollTop = prevScroll;
    else if (last !== null) { scroll.classList.add('ft-cc-in'); if (section) section.parentElement.classList.add('ft-cc-in'); }
    last = k;
    scroll.addEventListener('scroll', function () { cue(det); }, { passive: true });
    cue(det); setTimeout(function () { cue(det); }, 60);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { cue(det); });
    if (focused && focused.isConnected && focused !== document.activeElement) focused.focus({ preventScroll: true });
    busy = false;
  }

  /* The dock fits its content: the bar, the entries and the ask box, up to 40% of the panel (67% with Show more),
     never less than the bar, the newest entry and the ask box. Show more appears only when there is more to show. */
  var asked = false;
  try { asked = sessionStorage.getItem('ft-cc-asked') === '1'; } catch (e) {}
  (function () {
    var st = document.createElement('style');
    st.textContent = '.ft-cc-asked .ft-th__note { display: none; } .ft-cc-grow[hidden] { display: none !important; }';
    document.head.appendChild(st);
    if (asked) document.documentElement.classList.add('ft-cc-asked');
  })();
  function size(dock) {
    if (!dock || !dock.isConnected) return;
    var det = dock.parentElement, h = det ? det.clientHeight : 0;
    if (!h || window.innerWidth < 1024) { dock.style.height = ''; return; }
    var list = dock.querySelector('.ft-th__list'), grow = dock.querySelector('.ft-cc-grow');
    var keep = list ? list.scrollTop : 0, atEnd = list ? list.scrollHeight - list.scrollTop - list.clientHeight < 4 : true;
    dock.style.height = 'auto';
    var natural = dock.offsetHeight;
    var items = list ? list.querySelectorAll(':scope > *') : [], newest = items.length ? items[items.length - 1] : null;
    var floor = natural - (list ? list.offsetHeight : 0) + (newest ? newest.offsetHeight : 0) + 8;
    var cap = h * (tall ? 0.67 : 0.40);
    var target = Math.max(Math.min(natural, cap), Math.min(floor, h * 0.67));
    dock.style.height = Math.round(target) + 'px';
    if (grow) grow.hidden = !tall && natural <= h * 0.40 + 1;
    if (list) list.scrollTop = atEnd ? list.scrollHeight : keep;
  }
  /* The helper line under the ask box shows until the first question in this session, then hides everywhere */
  /* A page may clear the question before this runs, so it counts as asked when the thread grows after the submit */
  document.addEventListener('submit', function (e) {
    var f = e.target; if (!f || !f.closest || !f.closest('.ft-cc-dock')) return;
    var count = function () { var d = document.querySelector('.ft-cc-dock'), l = d && d.querySelector('.ft-th__list'); return l ? l.children.length : 0; };
    var q = f.querySelector('.ft-th__q'), had = !!(q && q.value.trim()), n0 = count();
    setTimeout(function () {
      if ((had || count() > n0) && !asked) { asked = true; try { sessionStorage.setItem('ft-cc-asked', '1'); } catch (e2) {} document.documentElement.classList.add('ft-cc-asked'); }
      size(document.querySelector('.ft-cc-dock'));
    }, 0);
  }, true);
  window.addEventListener('resize', function () { Array.prototype.forEach.call(document.querySelectorAll('.ft-cc-dock'), size); Array.prototype.forEach.call(document.querySelectorAll('.ft-cc'), cue); });

  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('.ft-cc-grow'); if (!b) return;
    tall = !tall; var dock = b.closest('.ft-cc-dock');
    size(dock);
    b.textContent = tall ? 'Show less' : 'Show more'; b.setAttribute('aria-expanded', String(tall));
    toEnd(dock); cue(dock.parentElement);
  });

  function start() {
    var det = document.getElementById('ch-detail'); if (!det) return;
    new MutationObserver(function () { if (!busy) arrange(); }).observe(det, { childList: true });
    arrange();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
