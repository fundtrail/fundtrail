# ViewerSheet

The frame of the viewer: a sheet over the app that opens one file at one passage. The document inside comes from a renderer for its type (ViewerText, ViewerEmail, ViewerPdf, ViewerPhoto).

```html
<div class="ft-scrim"></div>
<section class="ft-sheet" role="dialog" aria-modal="true" aria-labelledby="v-title" tabindex="-1">
  <header class="ft-sheet__head">
    <div class="ft-sheet__title">
      <h2 id="v-title">Award letter</h2>
      <span class="ft-sheet__meta"><span class="ft-id">award_letter.txt</span> · Uploaded by you · Jan 12, 2023</span>
    </div>
    <div class="ft-sheet__tools">
      <button class="ft-btn ft-btn--sm ft-btn--quiet">Download original</button><span class="ft-vr"></span>
      <button class="ft-iconbtn ft-iconbtn--close" aria-label="Close viewer"></button>
    </div>
  </header>
  <div class="ft-sheet__bar">
    <div class="ft-sheet__cite"><b>End date</b><span>Exact passage · line 15</span></div>
    <div class="ft-sheet__controls">
      <!-- PDFs and photos only: zoom -->
      <span class="ft-pager">
        <button class="ft-iconbtn ft-iconbtn--up" aria-label="Previous passage"></button>
        <span class="ft-pager__text">6 of 10</span>
        <button class="ft-iconbtn ft-iconbtn--down" aria-label="Next passage"></button>
      </span>
    </div>
  </div>
  <div class="ft-sheet__body">
    <div class="ft-sheet__doc"><!-- the renderer's document --></div>
    <aside class="ft-sheet__side">
      <div class="ft-sheet__section"><span class="ft-sheet__label">In this file</span><ul class="ft-sidefacts">…</ul></div>
      <div class="ft-sheet__section"><span class="ft-sheet__label">Linked to</span><ul class="ft-sidelinks">…</ul></div>
    </aside>
  </div>
</section>
```

- **Head:** title, then file name (`ft-id`), source and arrival date in `ft-sheet__meta`. Download original is quiet; Close is `ft-iconbtn--close`.
- **Bar:** `ft-sheet__cite` names the passage and says how exact it is. For photos and scans the second part is `<span class="ft-approx">Box checked by a second look</span>`. An unconfirmed fact says "Couldn't place this quote in the file" instead, and the document shows its page with the quote beside it and no highlight (ViewerUnconfirmed). Zoom (`ft-zoom`: minus, level, plus) appears only for PDFs and photos, before the pager.
- **Side:** each fact is a `button.ft-sidefact` (label, value, location); the active one has `aria-current="true"`. "Linked to" lists each charge's ID, name and the amount the file covers. A file of grant terms shows an `ft-sheet__note` instead.
- **Cards** use `ft-sheet ft-sheet--inline`, which drops the fixed position and the scrim.

**Opening it from the Demo.** Each trail link's name, and each decisive quote, is a button that opens the sheet at that link's file and passage. On open, the sheet takes focus and keeps it (Tab cycles inside). Esc, Close or a click on the scrim closes it, and focus goes back to the link that opened it. The up and down arrows, or the pager, move to the previous or next passage in the file; clicking a fact in the side list does the same.

**Contract fields:** `EvidenceFile` (name, source, sender, `arrived_at`), the citation's `location` (`char_location`, `page_location` or `image_box`) and `passage`, the file's facts, and its links with each charge's amount. `FileUrl` gives the original for Download original.

Under 900px wide the sheet fills the screen and the side list is hidden. Under reduced motion it jumps to the passage instead of scrolling.

Don't: crop the document to the passage, mark every cited passage at once, or call a photo's box exact.

**Hash params, for screenshots:** `#fact=N` picks a fact by index, and `&t=dark` sets the dark theme.
