/* FundTrail workspace and account menus, with the New workspace and Reset dialogs.
   Drop into any page that has the app shell: FTWorkspaceMenu.attach(options).
   It turns the sidebar's .ft-workspace block and its Account button into menu buttons.
   options: workspaces [{id, name, note, demo}], current (id), user {name, email},
            onNavigate(kind, value): kind is 'workspace' (value: id), 'new' (value: name), 'reset' (value: id) or 'signout'.
            Return false from onNavigate to skip the default (the default only updates the workspace button's label).
   Also: FTWorkspaceMenu.open('workspace' | 'account'), .dialog('new' | 'reset'), .close(). Plain ES5, no dependencies. */
(function () {
  var M = window.FTWorkspaceMenu = window.FTWorkspaceMenu || {};
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var opts = null, wsBtn = null, acBtn = null, menu = null, menuKind = null, dlg = null, scrim = null, seq = 0;
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function current() { for (var i = 0; i < opts.workspaces.length; i++) if (opts.workspaces[i].id === opts.current) return opts.workspaces[i]; return opts.workspaces[0]; }
  function nav(kind, value) { var r = opts.onNavigate ? opts.onNavigate(kind, value) : undefined; if (r !== false) feedback(kind, value); return r !== false; }
  /* Without a page handler, say what happened, so a choice never looks like it did nothing */
  var toastEl = null, toastTimer = null;
  function feedback(kind, value) {
    var name = value;
    if (kind === 'workspace' || kind === 'reset') for (var i = 0; i < opts.workspaces.length; i++) if (opts.workspaces[i].id === value) name = opts.workspaces[i].name;
    var text = kind === 'workspace' ? 'Switched to ' + name + '.' : kind === 'new' ? 'Created ' + name + '. It has no grants yet.' :
      kind === 'reset' ? name + ' is back to how it started.' : kind === 'signout' ? 'Signed out. The sign-in page opens next.' : '';
    if (!text) return;
    if (!toastEl) { toastEl = document.createElement('div'); toastEl.className = 'ft-toast'; toastEl.setAttribute('role', 'status'); document.body.appendChild(toastEl); }
    toastEl.textContent = text; toastEl.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { toastEl.hidden = true; }, 6000);
  }
  function syncLabel() { if (!wsBtn) return; var s = wsBtn.querySelector('span'); if (s) s.textContent = current().name; }

  /* ---------- menus ---------- */
  function items() { return menu ? Array.prototype.slice.call(menu.querySelectorAll('.ft-menu-item')) : []; }
  function focusItem(i) { var all = items(); if (!all.length) return; i = (i + all.length) % all.length; all[i].focus(); }
  function menuHtml(kind) {
    if (kind === 'account') {
      var u = opts.user;
      return '<div class="ft-menu-who" aria-hidden="true"><b>' + esc(u.name) + '</b><span>' + esc(u.email) + '</span><span>Signed in with Google</span></div>' +
        '<div class="ft-menu-sep" role="separator"></div>' +
        '<button type="button" class="ft-menu-item ft-menu-item--plain" role="menuitem" tabindex="-1" data-ft-menu="signout"><span class="ft-menu-item__text">Sign out</span></button>';
    }
    var h = '<div class="ft-menu-label" aria-hidden="true">Workspaces</div><div role="group" aria-label="Workspaces">';
    opts.workspaces.forEach(function (w) {
      var on = w.id === opts.current;
      h += '<button type="button" class="ft-menu-item" role="menuitemradio" aria-checked="' + on + '" tabindex="-1" data-ft-menu="workspace" data-ft-value="' + esc(w.id) + '">' +
        '<span class="ft-menu-item__mark" aria-hidden="true"></span><span class="ft-menu-item__text"><span>' + esc(w.name) + '</span>' + (w.note ? '<span class="ft-menu-item__sub">' + esc(w.note) + '</span>' : '') + '</span></button>';
    });
    h += '</div><div class="ft-menu-sep" role="separator"></div>' +
      '<button type="button" class="ft-menu-item" role="menuitem" tabindex="-1" data-ft-menu="new"><span class="ft-menu-item__mark ft-menu-item__mark--plus" aria-hidden="true"></span><span class="ft-menu-item__text">New workspace</span></button>';
    if (current().demo) h += '<button type="button" class="ft-menu-item ft-menu-item--danger" role="menuitem" tabindex="-1" data-ft-menu="reset"><span class="ft-menu-item__mark" aria-hidden="true"></span><span class="ft-menu-item__text">Reset demo workspace</span></button>';
    return h;
  }
  function open(kind, focusLast) {
    var btn = kind === 'account' ? acBtn : wsBtn; if (!btn) return;
    close(false);
    menu = document.createElement('div');
    menu.className = 'ft-menu' + (reduce ? '' : ' ft-menu--in');
    menu.id = 'ft-menu-' + kind; menu.setAttribute('role', 'menu');
    if (kind === 'account') menu.setAttribute('aria-label', 'Account: ' + opts.user.name + ', ' + opts.user.email + ', signed in with Google');
    else menu.setAttribute('aria-labelledby', btn.id);
    menu.innerHTML = menuHtml(kind);
    document.body.appendChild(menu); menuKind = kind;
    place();
    btn.setAttribute('aria-expanded', 'true'); btn.setAttribute('aria-controls', menu.id);
    menu.addEventListener('keydown', menuKey);
    menu.addEventListener('click', menuClick);
    var all = items(), checked = menu.querySelector('[aria-checked="true"]');
    if (focusLast) focusItem(all.length - 1); else if (checked) checked.focus(); else focusItem(0);
  }
  /* Keeps the menu next to its button: below the workspace block, above the Account button */
  function place() {
    if (!menu) return;
    var btn = menuKind === 'account' ? acBtn : wsBtn, r = btn.getBoundingClientRect();
    var vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
    menu.style.minWidth = Math.max(r.width, 248) + 'px';
    menu.style.left = Math.max(8, Math.min(r.left, vw - menu.offsetWidth - 8)) + 'px';
    if (menuKind === 'account') { menu.style.top = ''; menu.style.bottom = Math.max(8, vh - r.top + 6) + 'px'; }
    else { menu.style.bottom = ''; menu.style.top = Math.max(8, Math.min(r.bottom + 6, vh - menu.offsetHeight - 8)) + 'px'; }
  }
  function close(returnFocus) {
    if (!menu) return;
    var btn = menuKind === 'account' ? acBtn : wsBtn;
    menu.parentNode.removeChild(menu); menu = null; menuKind = null;
    if (btn) { btn.setAttribute('aria-expanded', 'false'); btn.removeAttribute('aria-controls'); if (returnFocus) btn.focus(); }
  }
  function menuKey(e) {
    var all = items(), i = all.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); focusItem(i + 1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); focusItem(i - 1); }
    else if (e.key === 'Home') { e.preventDefault(); focusItem(0); }
    else if (e.key === 'End') { e.preventDefault(); focusItem(all.length - 1); }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(true); }
    else if (e.key === 'Tab') { e.preventDefault(); close(true); }
    else if (e.key.length === 1 && /\S/.test(e.key)) {
      var k = e.key.toLowerCase();
      for (var n = 1; n <= all.length; n++) { var it = all[(i + n) % all.length]; if (it.textContent.trim().toLowerCase().charAt(0) === k) { it.focus(); break; } }
    }
  }
  function menuClick(e) {
    var t = e.target.closest ? e.target.closest('[data-ft-menu]') : null; if (!t) return;
    select(t.getAttribute('data-ft-menu'), t.getAttribute('data-ft-value'));
  }
  function select(kind, value) {
    if (kind === 'workspace') {
      close(true);
      if (value !== opts.current && nav('workspace', value)) { opts.current = value; syncLabel(); }
    } else if (kind === 'new' || kind === 'reset') { close(false); dialog(kind); }
    else if (kind === 'signout') { close(true); nav('signout'); }
  }

  /* ---------- dialogs ---------- */
  function dialogHtml(kind, id) {
    if (kind === 'reset') {
      return '<div class="ft-dialog-head"><h2 class="ft-dialog-title" id="' + id + '-t">Reset the demo workspace?</h2></div>' +
        '<div class="ft-dialog-body" id="' + id + '-d"><p>It goes back to how it started. This can’t be undone.</p>' +
        '<ul class="ft-dialog-list"><li>Your answers, confirmations, splits and sign-offs are removed.</li><li>Files you uploaded or forwarded to its grants are removed.</li>' +
        '<li>The clock goes back to where the demo starts.</li><li>Your other workspaces don’t change.</li></ul></div>' +
        '<div class="ft-dialog-foot"><button type="button" class="ft-btn" data-ft-dialog="cancel">Cancel</button><button type="button" class="ft-btn ft-btn--reject" data-ft-dialog="reset">Reset workspace</button></div>';
    }
    return '<form class="ft-dialog-form" novalidate><div class="ft-dialog-head"><h2 class="ft-dialog-title" id="' + id + '-t">New workspace</h2></div>' +
      '<div class="ft-dialog-body"><p id="' + id + '-d">A workspace holds its own grants, ledgers and evidence. Only you can see it.</p>' +
      '<div class="ft-field" id="' + id + '-field"><label class="ft-field__label" for="' + id + '-name">Name</label>' +
      '<input class="ft-input" id="' + id + '-name" name="name" autocomplete="off" placeholder="For example: Biology department" aria-describedby="' + id + '-help">' +
      '<span class="ft-field__hint" id="' + id + '-help">Add grants to it after you create it.</span></div></div>' +
      '<div class="ft-dialog-foot"><button type="button" class="ft-btn" data-ft-dialog="cancel">Cancel</button><button type="submit" class="ft-btn ft-btn--main" data-ft-dialog="create">Create workspace</button></div></form>';
  }
  function dialog(kind) {
    closeDialog(false); close(false);
    var id = 'ft-dialog-' + (++seq);
    scrim = document.createElement('div'); scrim.className = 'ft-scrim' + (reduce ? '' : ' ft-scrim--in');
    dlg = document.createElement('section');
    dlg.className = 'ft-dialog' + (reduce ? '' : ' ft-dialog--in');
    dlg.setAttribute('role', kind === 'reset' ? 'alertdialog' : 'dialog'); dlg.setAttribute('aria-modal', 'true');
    dlg.setAttribute('aria-labelledby', id + '-t'); dlg.setAttribute('aria-describedby', id + '-d'); dlg.tabIndex = -1;
    dlg.setAttribute('data-ft-kind', kind);
    dlg.innerHTML = dialogHtml(kind, id);
    var app = document.querySelector('.ft-app'); if (app) app.setAttribute('inert', '');
    document.body.appendChild(scrim); document.body.appendChild(dlg);
    scrim.addEventListener('click', function () { closeDialog(true); });
    dlg.addEventListener('keydown', dialogKey);
    dlg.addEventListener('click', dialogClick);
    var form = dlg.querySelector('form');
    if (form) {
      form.addEventListener('submit', function (e) { e.preventDefault(); e.stopPropagation(); create(id); });
      form.elements.name.addEventListener('input', function () { if (form.elements.name.value.trim()) fieldError(id, null); });
    }
    var first = kind === 'reset' ? dlg.querySelector('[data-ft-dialog="cancel"]') : dlg.querySelector('input');
    if (first) first.focus(); else dlg.focus();
  }
  function fieldError(id, msg) {
    var f = document.getElementById(id + '-field'), help = document.getElementById(id + '-help'), inp = document.getElementById(id + '-name');
    if (!f) return;
    f.classList.toggle('is-invalid', !!msg);
    if (msg) { inp.setAttribute('aria-invalid', 'true'); help.className = 'ft-field__error'; help.textContent = msg; }
    else { inp.removeAttribute('aria-invalid'); help.className = 'ft-field__hint'; help.textContent = 'Add grants to it after you create it.'; }
  }
  function create(id) {
    var inp = document.getElementById(id + '-name'), name = inp.value.replace(/\s+/g, ' ').trim();
    if (!name) { fieldError(id, 'Add a name.'); inp.focus(); return; }
    var taken = opts.workspaces.some(function (w) { return w.name.toLowerCase() === name.toLowerCase(); });
    if (taken) { fieldError(id, 'You already have a workspace with that name.'); inp.focus(); return; }
    if (nav('new', name)) {
      var wid = 'ws-' + Date.now().toString(36);
      opts.workspaces.push({ id: wid, name: name, note: 'No grants yet' }); opts.current = wid; syncLabel();
    }
    closeDialog(true);
  }
  function dialogClick(e) {
    var t = e.target.closest ? e.target.closest('[data-ft-dialog]') : null; if (!t) return;
    var a = t.getAttribute('data-ft-dialog');
    if (a === 'cancel') closeDialog(true);
    else if (a === 'reset') { var cur = opts.current; closeDialog(true); nav('reset', cur); }
  }
  function dialogKey(e) {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeDialog(true); return; }
    if (e.key !== 'Tab') return;
    var els = Array.prototype.filter.call(dlg.querySelectorAll('button:not([disabled]), input, [tabindex="0"]'), function (x) { return x.offsetParent !== null; });
    if (!els.length) return;
    var first = els[0], last = els[els.length - 1];
    if (e.shiftKey && (document.activeElement === first || document.activeElement === dlg)) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }
  function closeDialog(returnFocus) {
    if (!dlg) return;
    dlg.parentNode.removeChild(dlg); scrim.parentNode.removeChild(scrim); dlg = null; scrim = null;
    var app = document.querySelector('.ft-app'); if (app && !(window.FTViewer && window.FTViewer.isOpen && window.FTViewer.isOpen())) app.removeAttribute('inert');
    if (returnFocus && wsBtn) wsBtn.focus();
  }

  /* ---------- attach ---------- */
  function wire(btn, kind) {
    btn.setAttribute('aria-haspopup', 'menu'); btn.setAttribute('aria-expanded', 'false');
    btn.addEventListener('click', function (e) { e.preventDefault(); if (menu && menuKind === kind) close(true); else open(kind); });
    btn.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); open(kind); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); open(kind, true); }
    });
  }
  M.attach = function (o) {
    o = o || {};
    opts = {
      workspaces: [{ id: 'demo', name: 'Demo workspace', note: 'Sample grants. All data is synthetic.', demo: true }, { id: 'bio', name: 'Biology department', note: 'No grants yet' }],
      current: 'demo',
      user: { name: 'Taylor Example', email: 'taylor.example@university.example' },
      onNavigate: null
    };
    for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) opts[k] = o[k];
    var ws = document.querySelector('.ft-sidebar .ft-workspace');
    if (ws && ws.tagName !== 'BUTTON') {
      var b = document.createElement('button'); b.type = 'button'; b.className = ws.className; b.innerHTML = ws.innerHTML;
      ws.parentNode.replaceChild(b, ws); ws = b;
    }
    if (ws && !ws.classList.contains('ft-menu-trigger')) { ws.classList.add('ft-menu-trigger'); ws.id = ws.id || 'ft-menu-ws-btn'; wire(ws, 'workspace'); }
    wsBtn = ws; syncLabel();
    var ac = document.querySelector('.ft-sidebar .demo-footrow .ft-btn');
    if (!ac) { var bs = document.querySelectorAll('.ft-sidebar button'); for (var i = 0; i < bs.length; i++) if (bs[i].textContent.trim() === 'Account') { ac = bs[i]; break; } }
    if (ac && !ac.classList.contains('ft-menu-trigger')) { ac.classList.add('ft-menu-trigger'); ac.id = ac.id || 'ft-menu-ac-btn'; wire(ac, 'account'); }
    acBtn = ac;
    if (!M.attached) {
      document.addEventListener('mousedown', function (e) {
        if (!menu) return;
        var btn = menuKind === 'account' ? acBtn : wsBtn;
        if (!menu.contains(e.target) && !(btn && btn.contains(e.target))) close(false);
      }, true);
      window.addEventListener('resize', place);
      window.addEventListener('scroll', place, true);
    }
    M.attached = true;
    return M;
  };
  M.open = function (kind) { open(kind === 'account' ? 'account' : 'workspace'); };
  M.dialog = function (kind) { dialog(kind === 'reset' ? 'reset' : 'new'); };
  M.close = function () { close(false); closeDialog(false); };
  M.options = function () { return opts; };
})();
