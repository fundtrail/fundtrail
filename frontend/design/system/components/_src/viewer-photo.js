/* FundTrail viewer: photos and scans (F6, F7).
   A photo has no text layer and no OCR. The agent returns a box around each value, and a second look at the
   boxed area has to read the same value (decision 0012), so the box is drawn as checked, not approximate.
   A fact the second look couldn't confirm has confirmed:false; the frame then shows the whole photo with no box.
   Plain ES5, no dependencies. */
(function () {
  var V = window.FTViewer = window.FTViewer || {};
  V.files = V.files || {};

  var W = 480, H = 640;          /* the photo's own pixel size; 100% zoom shows it at this size */
  var PAD = 22, ANGLE = -2.5;    /* receipt margin and tilt, like a phone photo */
  var ZOOMS = [0.5, 0.75, 1, 1.5, 2, 2.5, 3];
  var DOC_W = 680;               /* the doc area's usual inner width in the sheet, used for the first view */
  var MONO = "'Geist Mono', ui-monospace, Menlo, monospace";

  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function r1(n) { return Math.round(n * 10) / 10; }

  /* Lay the receipt's lines out in the paper's own coordinates. */
  function layout(rc) {
    var y = 34, out = [], pw = rc.paperW;
    rc.lines.forEach(function (ln) {
      if (ln.gap) { y += ln.gap; return; }
      if (ln.rule) { out.push({ rule: true, y: y + 5 }); y += 12; return; }
      var size = ln.size || 12.5, lh = Math.round(size * 1.6), cw = size * 0.6;
      var x0, x1, tw = ln.text.length * cw;
      if (ln.align === 'center') { x0 = (pw - tw) / 2; x1 = x0 + tw; }
      else { x0 = PAD; x1 = ln.right ? pw - PAD : PAD + tw; }
      out.push({ text: ln.text, right: ln.right, align: ln.align, size: size, weight: ln.weight || 400, muted: ln.muted, key: ln.key,
        top: y, bottom: y + lh, base: y + Math.round(size * 1.15), x0: x0, x1: x1 });
      y += lh;
    });
    return { lines: out, h: y + 30 };
  }
  function place(rc) {
    var L = layout(rc), w = rc.paperW, h = L.h;
    var x = (W - w) / 2, y = Math.max(28, (H - h) / 2 - 8);
    return { L: L, x: x, y: y, w: w, h: h, cx: x + w / 2, cy: y + h / 2 };
  }
  function rotate(P, lx, ly) {
    var a = ANGLE * Math.PI / 180, X = P.x + lx - P.cx, Y = P.y + ly - P.cy;
    return [P.cx + X * Math.cos(a) - Y * Math.sin(a), P.cy + X * Math.sin(a) + Y * Math.cos(a)];
  }
  /* The agent's estimate: the lines for a fact, a little generous, as fractions of the photo. */
  function boxFor(rc, key) {
    var P = place(rc), ls = P.L.lines.filter(function (l) { return l.key === key; });
    var x0 = Math.min.apply(null, ls.map(function (l) { return l.x0; })) - 7, x1 = Math.max.apply(null, ls.map(function (l) { return l.x1; })) + 7;
    var y0 = Math.min.apply(null, ls.map(function (l) { return l.top; })) - 4, y1 = Math.max.apply(null, ls.map(function (l) { return l.bottom; })) + 3;
    var pts = [rotate(P, x0, y0), rotate(P, x1, y0), rotate(P, x1, y1), rotate(P, x0, y1)];
    var xs = pts.map(function (p) { return p[0]; }), ys = pts.map(function (p) { return p[1]; });
    var bx = Math.min.apply(null, xs), by = Math.min.apply(null, ys);
    var f = function (n) { return Math.round(n * 1000) / 1000; };
    return [f(bx / W), f(by / H), f((Math.max.apply(null, xs) - bx) / W), f((Math.max.apply(null, ys) - by) / H)];
  }
  function paperPath(w, h) {
    var t = 9, d = 3.5, s = 'M0 ' + d, x;
    for (x = 0; x < w; x += t) s += ' L' + r1(Math.min(w, x + t / 2)) + ' 0 L' + r1(Math.min(w, x + t)) + ' ' + d;
    s += ' L' + w + ' ' + (h - d);
    for (x = w; x > 0; x -= t) s += ' L' + r1(Math.max(0, x - t / 2)) + ' ' + h + ' L' + r1(Math.max(0, x - t)) + ' ' + (h - d);
    return s + ' Z';
  }
  function svg(file) {
    var rc = file.receipt, P = place(rc), id = 'ph-' + file.id;
    var s = '<svg class="ft-photo__img" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" aria-hidden="true" focusable="false">' +
      '<defs>' +
        '<linearGradient id="' + id + '-surf" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#454a50"/><stop offset="1" stop-color="#2a2e33"/></linearGradient>' +
        '<radialGradient id="' + id + '-vig" cx="0.5" cy="0.45" r="0.78"><stop offset="0.55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.34"/></radialGradient>' +
        '<linearGradient id="' + id + '-paper" x1="0" y1="0" x2="0.5" y2="1"><stop offset="0" stop-color="#f8f6f0"/><stop offset="1" stop-color="#e9e5da"/></linearGradient>' +
        '<filter id="' + id + '-sh" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="7" stdDeviation="9" flood-color="#000" flood-opacity="0.38"/></filter>' +
      '</defs>' +
      '<rect width="' + W + '" height="' + H + '" fill="url(#' + id + '-surf)"/>' +
      '<g transform="rotate(' + ANGLE + ' ' + r1(P.cx) + ' ' + r1(P.cy) + ') translate(' + r1(P.x) + ' ' + r1(P.y) + ')">' +
      '<path d="' + paperPath(P.w, P.h) + '" fill="url(#' + id + '-paper)" filter="url(#' + id + '-sh)"/>' +
      '<g font-family="' + MONO + '" fill="#2b2c30" fill-opacity="0.86">';
    P.L.lines.forEach(function (l) {
      if (l.rule) { s += '<line x1="' + PAD + '" x2="' + (P.w - PAD) + '" y1="' + l.y + '" y2="' + l.y + '" stroke="#8b8a85" stroke-width="1" stroke-dasharray="3 3"/>'; return; }
      var attrs = ' font-size="' + l.size + '" font-weight="' + l.weight + '"' + (l.muted ? ' fill-opacity="0.6"' : '');
      if (l.align === 'center') s += '<text x="' + r1(P.w / 2) + '" y="' + l.base + '" text-anchor="middle"' + attrs + '>' + esc(l.text) + '</text>';
      else {
        s += '<text x="' + PAD + '" y="' + l.base + '"' + attrs + '>' + esc(l.text) + '</text>';
        if (l.right) s += '<text x="' + (P.w - PAD) + '" y="' + l.base + '" text-anchor="end"' + attrs + '>' + esc(l.right) + '</text>';
      }
    });
    return s + '</g></g><rect width="' + W + '" height="' + H + '" fill="url(#' + id + '-vig)"/></svg>';
  }
  function snap(z) {
    var best = ZOOMS[0];
    ZOOMS.forEach(function (s) { if (Math.abs(s - z) < Math.abs(best - z)) best = s; });
    return best;
  }
  function padOf(el) { var cs = getComputedStyle(el); return { x: parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight), y: parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom) }; }

  V.photo = {
    zooms: ZOOMS,
    /* Opens zoomed to the fact's box: the box takes about half the visible width. */
    initialView: function (file, active) {
      var b = file.facts[active].box;
      return { zoom: snap(DOC_W * 0.5 / (b[2] * W)), whole: false };
    },
    render: function (file, active, view) {
      view = view || V.photo.initialView(file, active);
      var f = file.facts[active], b = f.box;
      var size = view.whole ? '' : ' style="width:' + Math.round(W * view.zoom) + 'px;height:' + Math.round(H * view.zoom) + 'px"';
      return '<div class="ft-photo' + (view.whole ? ' ft-photo--whole' : '') + '">' +
        '<div class="ft-photo__tools"><button type="button" class="ft-btn ft-btn--sm ft-photo__toggle" data-act="whole" aria-pressed="' + !!view.whole + '">' + V.photo.toggleLabel(view) + '</button></div>' +
        '<div class="ft-photo__stage"><div class="ft-photo__frame"' + size + ' role="img" aria-label="' + esc('Photo of a receipt from ' + file.receipt.vendor + '. The outlined box around ' + f.label.toLowerCase() + ' was checked by a second look.') + '">' +
        svg(file) +
        '<span class="ft-box ft-photo__box" data-photo-box style="left:' + r1(b[0] * 100) + '%;top:' + r1(b[1] * 100) + '%;width:' + r1(b[2] * 100) + '%;height:' + r1(b[3] * 100) + '%"></span>' +
        '</div></div></div>';
    },
    target: function (docEl) { return docEl.querySelector('[data-photo-box]'); },
    /* Optional helpers for the frame. */
    center: function (docEl, smooth) {
      var box = docEl.querySelector('[data-photo-box]'); if (!box) return;
      var d = docEl.getBoundingClientRect(), b = box.getBoundingClientRect();
      docEl.scrollTo({ top: Math.max(0, docEl.scrollTop + b.top - d.top + b.height / 2 - docEl.clientHeight / 2),
        left: Math.max(0, docEl.scrollLeft + b.left - d.left + b.width / 2 - docEl.clientWidth / 2), behavior: smooth ? 'smooth' : 'instant' });
    },
    fitZoom: function (docEl) { var p = padOf(docEl); return Math.min((docEl.clientWidth - p.x) / W, (docEl.clientHeight - p.y) / H); },
    levelText: function (view, docEl) { return Math.round((view.whole && docEl ? V.photo.fitZoom(docEl) : view.zoom) * 100) + '%'; },
    toggleLabel: function (view) { return view.whole ? 'Zoom to the box' : 'Show whole photo'; },
    /* Zoom one step in (dir 1) or out (dir -1). From the whole photo, it starts at the fitted size. */
    step: function (view, dir, docEl) {
      var z = view.whole && docEl ? V.photo.fitZoom(docEl) : view.zoom, next = null;
      ZOOMS.forEach(function (s) { if (dir > 0 && s > z + 0.001 && next === null) next = s; if (dir < 0 && s < z - 0.001) next = s; });
      return next === null ? view : { zoom: next, whole: false };
    },
    canStep: function (view, dir, docEl) { return V.photo.step(view, dir, docEl) !== view; }
  };

  function photoFile(f) {
    f.facts.forEach(function (x) { x.box = boxFor(f.receipt, x.key); x.loc = ''; });
    return f;
  }
  V.files.F6 = photoFile({
    id: 'F6', type: 'photo', name: 'boat_rental_receipt.jpg', title: 'Receipt photo',
    meta: 'Gmail · from robin.example@university.example · Apr 12, 2026',
    receipt: { vendor: 'Example Marina', paperW: 286, lines: [
      { text: 'EXAMPLE MARINA', align: 'center', size: 19, weight: 700, key: 'vendor' },
      { text: 'Harbor Rd, Example Bay', align: 'center', size: 11, muted: true },
      { gap: 6 }, { rule: true },
      { text: 'Jan 14, 2026', size: 12.5, key: 'date' },
      { rule: true },
      { text: 'Boat rental, full day', right: '$1,400.00', size: 12 },
      { text: 'Fuel', right: '$80.00', size: 12 },
      { rule: true },
      { text: 'TOTAL', right: '$1,480.00', size: 14.5, weight: 700, key: 'total' },
      { gap: 14 },
      { text: 'Thank you.', align: 'center', size: 11.5 },
      { gap: 10 },
      { text: 'SYNTHETIC DEMO', align: 'center', size: 9, muted: true }
    ] },
    facts: [
      { label: 'Vendor', value: 'Example Marina', key: 'vendor' },
      { label: 'Date', value: 'Jan 14, 2026', key: 'date' },
      { label: 'Total', value: '$1,480.00', key: 'total' }
    ],
    links: [{ id: 'L-1015', name: 'Field boat rental', amount: '$1,480.00 of $1,480.00' }], note: '',
    active: 2
  });
  V.files.F7 = photoFile({
    id: 'F7', type: 'photo', name: 'field_camera_receipt.jpg', title: 'Receipt photo',
    meta: 'Uploaded by you · Jan 22, 2026',
    receipt: { vendor: 'Example Optics Supply', paperW: 292, lines: [
      { text: 'EXAMPLE OPTICS SUPPLY', align: 'center', size: 16.5, weight: 700, key: 'vendor' },
      { gap: 6 }, { rule: true },
      { text: 'Field camera,', size: 12, key: 'item' },
      { text: 'microscope mount', right: '$1,325.00', size: 12, key: 'item' },
      { rule: true },
      { text: 'TOTAL', right: '$1,325.00', size: 14.5, weight: 700, key: 'total' },
      { gap: 8 },
      { text: 'Jan 21, 2026', size: 12.5, key: 'date' },
      { gap: 14 },
      { text: 'SYNTHETIC DEMO', align: 'center', size: 9, muted: true }
    ] },
    facts: [
      { label: 'Vendor', value: 'Example Optics Supply', key: 'vendor' },
      { label: 'Date', value: 'Jan 21, 2026', key: 'date' },
      { label: 'Item', value: 'Field camera, microscope mount', key: 'item' },
      { label: 'Total', value: '$1,325.00', key: 'total' }
    ],
    links: [{ id: 'L-1019', name: 'Field microscope camera', amount: '$1,325.00 of $1,325.00' }], note: '',
    active: 3
  });
})();
