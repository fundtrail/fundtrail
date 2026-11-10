/* FundTrail viewer: PDF renderer (FTViewer.pdf) and the F5 demo file.
   Pages are drawn in HTML at US Letter proportions: 612 x 792 at 100%, sized in em so
   one CSS variable (--ft-pdf-z) scales the whole page. The active fact's exact text gets
   mark.ft-mark-hl.is-active. Plain ES5, no dependencies. */
(function () {
  window.FTViewer = window.FTViewer || {};
  FTViewer.files = FTViewer.files || {};

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; });
  }

  /* Write a block's text, marking the active fact's passage when it lives in this block.
     A fact names its page, its exact text and, when the text appears twice, its block. */
  function writeText(blockId, pageIndex, text, fact) {
    var hit = fact && fact.page === pageIndex + 1 && (!fact.block || fact.block === blockId) ? text.indexOf(fact.text) : -1;
    if (hit < 0) return esc(text);
    return esc(text.slice(0, hit)) +
      '<mark class="ft-mark-hl is-active" data-ft-active="1">' + esc(fact.text) + '</mark>' +
      esc(text.slice(hit + fact.text.length));
  }

  function block(b, p, fact) {
    var t = function (id, text) { return writeText(id, p, text, fact); };
    switch (b.kind) {
      case 'notice': return '<p class="ft-pdf__notice">' + t(b.id, b.text) + '</p>';
      case 'cols':
        return '<div class="ft-pdf__cols">' + b.cols.map(function (col, i) {
          return '<div class="ft-pdf__col' + (i ? ' ft-pdf__col--end' : '') + '">' + col.map(function (c) { return block(c, p, fact); }).join('') + '</div>';
        }).join('') + '</div>';
      case 'h1': return '<p class="ft-pdf__vendor">' + t(b.id, b.text) + '</p>';
      case 'h2': return '<p class="ft-pdf__docno">' + t(b.id, b.text) + '</p>';
      case 'table':
        return '<table class="ft-pdf__table"><thead><tr>' + b.head.map(function (h, i) {
          return '<th' + (i ? ' class="is-num"' : '') + '>' + esc(h) + '</th>';
        }).join('') + '</tr></thead><tbody>' + b.rows.map(function (row, r) {
          return '<tr>' + row.map(function (cell, c) {
            return '<td' + (c ? ' class="is-num"' : '') + '>' + t(b.id + '.' + r + '.' + c, cell) + '</td>';
          }).join('') + '</tr>';
        }).join('') + '</tbody></table>';
      case 'total': return '<p class="ft-pdf__total">' + t(b.id, b.text) + '</p>';
      case 'small': return '<p class="ft-pdf__small">' + t(b.id, b.text) + '</p>';
      default: return '<p class="ft-pdf__p">' + t(b.id, b.text) + '</p>';
    }
  }

  FTViewer.pdf = {
    zooms: [0.75, 1, 1.25, 1.5, 2],
    initialView: function () { return { zoom: 1, whole: false }; },
    render: function (file, active, view) {
      var fact = file.facts[active], z = (view && view.zoom) || 1, n = file.pages.length;
      return '<div class="ft-pdf" style="--ft-pdf-z:' + z + '">' + file.pages.map(function (page, p) {
        return '<figure class="ft-pdf__sheet" aria-label="Page ' + (p + 1) + ' of ' + n + '">' +
          '<div class="ft-pdf__page"><div class="ft-pdf__text">' + page.blocks.map(function (b) { return block(b, p, fact); }).join('') + '</div></div>' +
          '<figcaption class="ft-pdf__label">Page ' + (p + 1) + ' of ' + n + '</figcaption></figure>';
      }).join('') + '</div>';
    },
    target: function (docEl) { return docEl.querySelector('[data-ft-active]'); }
  };

  FTViewer.files.F5 = {
    id: 'F5', type: 'pdf', name: 'invoice_SEQ-0311.pdf', title: 'Invoice SEQ-0311',
    meta: 'Gmail attachment · from billing@sequencing.example · Jan 12, 2026',
    links: [{ id: 'L-1010', name: 'Sequencing core, shared run 6', amount: '$5,833.33 charged. This grant’s part isn’t on file.' }],
    note: '',
    pages: [
      { blocks: [
        { kind: 'notice', id: 'notice', text: 'SYNTHETIC DEMO DOCUMENT. Not issued by any company. Created for the FundTrail demo.' },
        { kind: 'cols', cols: [
          [{ kind: 'h1', id: 'vendor', text: 'Example Sequencing Core' }, { kind: 'p', id: 'addr', text: '1 Example Way, Example City' }],
          [{ kind: 'h2', id: 'docno', text: 'INVOICE SEQ-0311' }, { kind: 'p', id: 'date', text: 'Invoice Date: January 6, 2026' }]
        ] },
        { kind: 'p', id: 'bill', text: 'Bill To: Dr. Robin Example, Example State University' },
        { kind: 'table', id: 'items', head: ['Description', 'Qty', 'Amount'], rows: [['Sediment DNA sequencing, shared run 6', '96 samples', '$10,000.00']] },
        { kind: 'small', id: 'note', text: 'Note: Run shared by awards SYN-2300117 and SYN-2300245.' },
        { kind: 'total', id: 'total', text: 'Total Due: $10,000.00' }
      ] },
      { blocks: [
        { kind: 'p', id: 'terms', text: 'Payment terms. Net 30 days from the invoice date. Remit to Example Sequencing Core, 1 Example Way, Example City.' },
        { kind: 'p', id: 'questions', text: 'Questions: billing@sequencing.example' }
      ] }
    ],
    facts: [
      { label: 'Invoice', value: 'SEQ-0311', page: 1, block: 'docno', text: 'INVOICE SEQ-0311' },
      { label: 'Invoice date', value: 'Jan 6, 2026', page: 1, block: 'date', text: 'January 6, 2026' },
      { label: 'Service', value: 'Shared run 6, 96 samples', page: 1, block: 'items.0.0', text: 'Sediment DNA sequencing, shared run 6' },
      { label: 'Shared by', value: 'SYN-2300117 and SYN-2300245', page: 1, block: 'note', text: 'Run shared by awards SYN-2300117 and SYN-2300245.' },
      { label: 'Total', value: '$10,000.00', page: 1, block: 'total', text: '$10,000.00' },
      { label: 'Payment terms', value: 'Net 30 days', page: 2, block: 'terms', text: 'Net 30 days from the invoice date.' }
    ],
    active: 4
  };
})();
