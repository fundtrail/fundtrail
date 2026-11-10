/* The evidence report in the viewer sheet: its pages in the document area, its parts in the side list.
   FTReport.open(opener) needs window.FTReportPages (the pages' HTML), built into the card. */
(function () {
  var V = window.FTViewer = window.FTViewer || {};
  V.report = {
    zooms: [0.5, 0.65, 0.8, 1, 1.25],
    initialView: function () { return { zoom: 0.8, whole: false }; },
    cite: function (file, f) { return '<b>' + f.label + '</b><span>Page ' + f.page + ' of ' + file.pages + '</span>'; },
    render: function (file, active, view) { return '<div class="ft-report ft-report--sheet" style="zoom:' + view.zoom + '">' + file.html + '</div>'; },
    target: function (docEl, file, active) {
      var f = file.facts[active], el = f.sel ? docEl.querySelector(f.sel) : null;
      return el || docEl.querySelector('#rp-' + f.page);
    }
  };
  window.FTReport = {
    file: function () {
      var signed = document.documentElement.classList.contains('is-signed');
      var d = window.FTReportData || { counts: {}, grant: {} };
      var open = (d.counts.conflict || 0) + (d.counts.human || 0) + (d.counts.missing || 0);
      return {
        id: 'R1', type: 'report', name: 'evidence_report_SYN-2300117.pdf', title: 'Evidence report', pages: 9,
        meta: (signed ? 'Signed off by you · Apr 12, 2026' : 'Draft · As of Apr 12, 2026') + ' · 9 pages',
        html: (function (h) {
          if (!signed || !window.FTReportNote) return h;
          var t = document.createElement('div'); t.innerHTML = h;
          var n = t.querySelector('.ft-rso-note'); if (n) n.textContent = window.FTReportNote;
          return t.innerHTML;
        })(window.FTReportPages || ''),
        facts: [
          { label: 'Summary', value: 'The award, its total and its buckets', page: 1 },
          { label: 'All charges', value: (d.charges ? d.charges.length : 51) + ' charges, ' + (d.grant.charged || ''), page: 2 },
          { label: 'Charge sections', value: 'Checks, quotes and history', page: 4 },
          { label: 'Open at sign-off', value: open + ' charges', page: 7 },
          { label: 'Sign-off', value: signed ? 'Signed off Apr 12, 2026' : 'Not signed off yet', page: 7, sel: '#rp-7 .ft-rso-party' },
          { label: 'Sources', value: 'Every file the report cites', page: 8 }
        ],
        links: [],
        note: signed ? 'Signed off. Attach it to the Award Closeout Certification in BFS.' : 'Draft. It regenerates whenever a record changes, until you sign off.'
      };
    },
    open: function (opener, part) { var f = this.file(); V.open(f, part || 0, opener); }
  };
})();
