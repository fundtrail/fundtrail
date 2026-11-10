/* FundTrail viewer: plain text and email renderers, with files F1 to F4.
   Plain ES5, no dependencies. See viewer-spec.md for the interface. */
(function () {
  var V = window.FTViewer = window.FTViewer || {};
  V.files = V.files || {};

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* Wrap the active fact's exact text in a mark, if this is its line. */
  function markText(str, n, file, active) {
    var f = file.facts[active];
    if (!f || f.line !== n) return esc(str);
    var i = str.indexOf(f.text);
    if (i < 0) return '<mark class="ft-mark-hl is-active">' + esc(str) + '</mark>';
    return esc(str.slice(0, i)) + '<mark class="ft-mark-hl is-active">' + esc(f.text) + '</mark>' + esc(str.slice(i + f.text.length));
  }
  function isCited(n, file, active) { var f = file.facts[active]; return !!f && f.line === n; }

  function row(n, html, file, active, extra) {
    return '<div class="ft-doc-text__row' + (isCited(n, file, active) ? ' is-cited' : '') + '" data-line="' + n + '">' +
      '<span class="ft-doc-text__n" aria-hidden="true">' + n + '</span>' +
      '<span class="ft-doc-text__t' + (extra || '') + '">' + (html || '&#8203;') + '</span></div>';
  }

  /* ---------- plain text: every line with its number ---------- */
  V.text = {
    render: function (file, active) {
      var out = '<div class="ft-doc-text" role="document" aria-label="' + esc(file.name) + '">';
      for (var i = 0; i < file.lines.length; i++) out += row(i + 1, markText(file.lines[i], i + 1, file, active), file, active);
      return out + '</div>';
    },
    target: function (docEl) { return docEl.querySelector('mark.ft-mark-hl.is-active'); }
  };

  /* ---------- email: headers as key-value rows, then the body ---------- */
  var SHOWN = { From: 1, To: 1, Subject: 1, Date: 1, Cc: 1 };
  V.email = {
    render: function (file, active) {
      var lines = file.lines, head = '', body = '', i = 0;
      for (; i < lines.length && lines[i] !== ''; i++) {
        var m = /^([A-Za-z-]+):\s?(.*)$/.exec(lines[i]);
        if (!m || !SHOWN[m[1]]) continue;
        var n = i + 1, f = file.facts[active], val = m[2];
        var v = f && f.line === n ? markText(val, n, file, active) : esc(val);
        head += '<div class="ft-doc-email__hrow' + (isCited(n, file, active) ? ' is-cited' : '') + (m[1] === 'Subject' ? ' is-subject' : '') + '" data-line="' + n + '">' +
          '<span class="ft-doc-text__n" aria-hidden="true">' + n + '</span><span class="ft-doc-email__k">' + esc(m[1]) + '</span><span class="ft-doc-email__v">' + v + '</span></div>';
      }
      for (i = i + 1; i < lines.length; i++) {
        var ln = lines[i], reply = /^>/.test(ln);
        body += row(i + 1, markText(reply ? ln.replace(/^>\s?/, '') : ln, i + 1, file, active), file, active, reply ? ' is-reply' : '');
      }
      return '<div class="ft-doc-text ft-doc-email" role="document" aria-label="' + esc(file.name) + '"><div class="ft-doc-email__head">' + head + '</div>' + body + '</div>';
    },
    target: function (docEl) { return docEl.querySelector('mark.ft-mark-hl.is-active'); }
  };

  /* ---------- the files ---------- */
  V.files.F1 = {
    id: 'F1', type: 'text', name: 'award_letter.txt', title: 'Award letter', meta: 'Uploaded by you · Jan 12, 2023',
    links: [], note: 'Grant terms. Confirmed by you, Jan 12, 2023.',
    lines: [
      'SYNTHETIC DEMO DOCUMENT. Not issued by any agency. Created for the FundTrail golden fixture.',
      '',
      'AWARD NOTICE',
      'Award Number: SYN-2300117',
      'Date: January 10, 2023',
      'Recipient: Example State University',
      'Project Title: Sediment Microbiome Survey of Example Bay',
      '',
      'Principal Investigator: Dr. Robin Example, robin.example@university.example',
      '',
      'Program Officer: Dr. Jesse Sample, jesse.sample@funder.example',
      '',
      'Grants Officer: Casey Placeholder, casey.placeholder@funder.example',
      '',
      'Period of Performance. The period of performance for this award is February 1, 2023 through January 31, 2026. Costs must be incurred within the period of performance to be charged to this award.',
      '',
      'Budget. Materials and Supplies: $40,000. Other Direct Costs: $60,000. Participant Support Costs: $20,000.',
      '',
      'Prior Approval. Funds budgeted for Participant Support Costs may not be used for other categories of expense without prior written approval from the Program Officer, requested through Research.gov.'
    ],
    facts: [
      { label: 'Award', value: 'SYN-2300117', line: 4, text: 'SYN-2300117' },
      { label: 'Dated', value: 'Jan 10, 2023', line: 5, text: 'January 10, 2023' },
      { label: 'Principal investigator', value: 'Dr. Robin Example', line: 9, text: 'Dr. Robin Example, robin.example@university.example' },
      { label: 'Program officer', value: 'Dr. Jesse Sample', line: 11, text: 'Dr. Jesse Sample, jesse.sample@funder.example' },
      { label: 'Grants officer', value: 'Casey Placeholder', line: 13, text: 'Casey Placeholder, casey.placeholder@funder.example' },
      { label: 'End date', value: 'Jan 31, 2026', line: 15, text: 'February 1, 2023 through January 31, 2026' },
      { label: 'Materials and Supplies', value: '$40,000.00', line: 17, text: 'Materials and Supplies: $40,000' },
      { label: 'Other Direct Costs', value: '$60,000.00', line: 17, text: 'Other Direct Costs: $60,000' },
      { label: 'Participant Support Costs', value: '$20,000.00', line: 17, text: 'Participant Support Costs: $20,000' },
      { label: 'Approval rule', value: 'Program officer, through Research.gov', line: 19, text: 'without prior written approval from the Program Officer, requested through Research.gov' }
    ],
    active: 5
  };

  V.files.F2 = {
    id: 'F2', type: 'text', name: 'extension_notice.txt', title: 'Award amendment 01', meta: 'Google Drive · Apr 10, 2026',
    links: [], note: 'Waiting for you: confirm or reject the new end date.',
    lines: [
      'SYNTHETIC DEMO DOCUMENT. Not issued by any agency. Created for the FundTrail golden fixture.',
      '',
      'AWARD AMENDMENT',
      'Award Number: SYN-2300117',
      'Amendment Number: 01',
      'Date: January 15, 2026',
      '',
      'No-Cost Extension. The end date of the period of performance for this award is changed from January 31, 2026 to January 31, 2027. No additional funds are provided by this amendment.',
      '',
      'All other terms and conditions of the award remain unchanged.',
      '',
      'Casey Placeholder, Grants Officer'
    ],
    facts: [
      { label: 'Amendment', value: '01', line: 5, text: 'Amendment Number: 01' },
      { label: 'Dated', value: 'Jan 15, 2026', line: 6, text: 'January 15, 2026' },
      { label: 'New end date', value: 'Jan 31, 2027', line: 8, text: 'changed from January 31, 2026 to January 31, 2027' },
      { label: 'Signed by', value: 'Casey Placeholder, Grants Officer', line: 12, text: 'Casey Placeholder, Grants Officer' }
    ],
    active: 2
  };

  V.files.F3 = {
    id: 'F3', type: 'email', name: 'sequencing_invoice.eml', title: 'Email from Dr. Robin Example', meta: 'Gmail · Feb 21, 2026',
    links: [{ id: 'L-1002', name: 'Sediment DNA sequencing run 7', amount: '$2,180.00 of $2,180.00' }], note: '',
    lines: [
      'From: Dr. Robin Example <robin.example@university.example>',
      'To: grant-inbox@fundtrail.example',
      'Subject: Sequencing invoice for run 7',
      'Date: Sat, 21 Feb 2026 09:30:00 -0800',
      'Content-Type: text/plain; charset=utf-8',
      '',
      'SYNTHETIC DEMO DOCUMENT. Not sent by any real person. Created for the FundTrail golden fixture.',
      '',
      'Hi, the sequencing core invoice for the Example Bay samples is below.',
      '',
      'INVOICE SEQ-0207',
      'Example Sequencing Core',
      'Invoice Date: February 20, 2026',
      'Service: Sediment DNA sequencing, run 7, 48 samples',
      '',
      'Total Due: $2,180.00'
    ],
    facts: [
      { label: 'Sender', value: 'Dr. Robin Example, principal investigator', line: 1, text: 'robin.example@university.example' },
      { label: 'Invoice', value: 'SEQ-0207', line: 11, text: 'INVOICE SEQ-0207' },
      { label: 'Invoice date', value: 'Feb 20, 2026', line: 13, text: 'February 20, 2026' },
      { label: 'Service', value: 'Sequencing run 7, 48 samples', line: 14, text: 'Sediment DNA sequencing, run 7, 48 samples' },
      { label: 'Total', value: '$2,180.00', line: 16, text: '$2,180.00' }
    ],
    active: 4
  };

  V.files.F4 = {
    id: 'F4', type: 'email', name: 'approval_email.eml', title: 'Email from Dr. Robin Example', meta: 'Gmail · Oct 6, 2025',
    links: [{ id: 'L-0981', name: 'Conference registration', amount: 'Approval' }], note: '',
    lines: [
      'From: Dr. Robin Example <robin.example@university.example>',
      'To: Sam Example <sam.example@university.example>',
      'Subject: Re: Ocean Sciences Meeting registration',
      'Date: Thu, 2 Oct 2025 16:12:00 -0700',
      'Content-Type: text/plain; charset=utf-8',
      '',
      'SYNTHETIC DEMO DOCUMENT. Not sent by any real person. Created for the FundTrail demo.',
      '',
      'Approved, go ahead and register.',
      '',
      'Robin',
      '',
      '> Could I register for the Example Ocean Sciences Meeting? The fee is $650.'
    ],
    facts: [
      { label: 'Approver', value: 'Dr. Robin Example, principal investigator', line: 1, text: 'robin.example@university.example' },
      { label: 'Approval', value: 'Approved by email', line: 9, text: 'Approved, go ahead and register.' },
      { label: 'What it approves', value: 'Meeting registration, $650.00', line: 13, text: 'The fee is $650.' }
    ],
    active: 1
  };
})();
