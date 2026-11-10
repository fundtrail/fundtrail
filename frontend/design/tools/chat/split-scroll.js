/* The standard layout without a thread dock, for pages whose items have no review thread (Evidence, Grant terms).
   The grant header stays put; under it the list and the selected item fill the rest of the screen and scroll on
   their own, with the same proportions and the same quiet transition as the grant page and Charges (chat-c.js).
   Below 1024px wide the page falls back to one normal scroll. */
(function () {
  var css = '' +
    '.ft-app { min-height: 0 !important; height: 100vh; }' +
    '.ft-sidebar { position: sticky !important; top: 0; height: 100vh !important; overflow-y: auto; }' +
    '.ft-main { height: 100vh; min-height: 0; overflow: hidden; }' +
    '.ft-content { flex: 1; min-height: 0; overflow: hidden; }' +
    '.ft-content > .ft-split { flex: 1; min-height: 0; align-items: stretch; }' +
    '.ft-content > .ft-split > * { min-height: 0; overflow-y: auto; overscroll-behavior: contain; }' +
    '.ft-content > .ft-split > .demo-col { padding-bottom: var(--space-4); }' +
    '.ft-ev-scroll { max-height: none !important; overflow: visible !important; }' +
    '.ft-toast { left: calc(var(--sidebar-width) + 24px) !important; transform: none !important; }' +
    '@media (prefers-reduced-motion: no-preference) { .ft-ss-in { animation: ft-ss-in 160ms ease both; } }' +
    '@keyframes ft-ss-in { from { opacity: 0; transform: translateX(10px); } to { opacity: 1; transform: none; } }' +
    '@media (max-width: 1023px) { .ft-app, .ft-main, .ft-content { height: auto; overflow: visible; } .ft-content > .ft-split > * { overflow: visible; } .ft-ev-scroll { max-height: max(360px, calc(100vh - 330px)) !important; overflow-y: auto !important; } }';
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  /* The selected item's panel: when a different item opens, it starts at its top and slides in quietly;
     a redraw of the same item (Confirm, Undo, an inline form) keeps its scroll position. */
  var PANELS = ['ev-detail', 'gt-detail'];
  function key(p) { var t = p.querySelector('h2, .ft-charge-title, .ft-gt-detail__title'); return t ? t.textContent : ''; }
  function watch(p) {
    var last = key(p), pos = 0;
    p.addEventListener('scroll', function () { pos = p.scrollTop; }, { passive: true });
    new MutationObserver(function () {
      var k = key(p);
      if (k === last) { if (p.scrollTop !== pos) p.scrollTop = pos; return; }
      last = k; p.scrollTop = 0; pos = 0;
      p.classList.remove('ft-ss-in'); void p.offsetWidth; p.classList.add('ft-ss-in');
    }).observe(p, { childList: true });
  }

  /* Keep the selected row in view inside its own scrolling column when the keyboard moves the selection */
  document.addEventListener('keydown', function (e) {
    if (['ArrowDown', 'ArrowUp', 'Home', 'End'].indexOf(e.key) < 0) return;
    setTimeout(function () { var r = document.activeElement; if (r && r.closest && r.closest('.ft-split') && r.scrollIntoView) r.scrollIntoView({ block: 'nearest' }); }, 0);
  });

  function start() { PANELS.forEach(function (id) { var p = document.getElementById(id); if (p) watch(p); }); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
