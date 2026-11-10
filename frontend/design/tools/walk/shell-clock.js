/* The walkthrough's demo clock, shared by the Walkthrough card and the screens page.
   The grant page reports where its clock is ({ftClock: {date, step}}); other screens open at the matching date
   where they have one, and say so where they only exist at Apr 12. */
var FTWalkClock = (function () {
  var DATES = { 0: 'Apr 9, 2026', 2: 'Apr 10, 2026', 3: 'Apr 10, 2026', 4: 'Apr 12, 2026' };
  var ONLY12 = { charges: 1, evidence: 1, closeout: 1, report: 1 };
  var step = 0;
  try { var s = sessionStorage.getItem('ft-walk-step'); if (s !== null && DATES[+s]) step = +s; } catch (e) {}
  function save() { try { sessionStorage.setItem('ft-walk-step', String(step)); } catch (e) {} }
  return {
    step: function () { return step; },
    label: function () { return 'Demo clock: ' + DATES[step]; },
    set: function (n) { if (DATES[n] !== undefined && n !== step) { step = n; save(); return true; } return false; },
    reset: function () { step = 0; save(); },
    /* The hash a screen opens with, given the clock */
    hashFor: function (m) {
      if (m.id === 'grant') return 's=' + step;
      if (m.id === 'terms') return step === 2 ? 'at=apr10' : m.hash;
      if (m.id === 'home') return step === 0 ? 'at=apr9' : m.hash;
      return m.hash;
    },
    /* True when the screen can only show Apr 12 and the clock is earlier */
    shownLater: function (m) {
      if (step >= 4) return false;
      if (ONLY12[m.id]) return true;
      if (m.id === 'terms') return step !== 2;
      if (m.id === 'home') return step === 2 || step === 3;
      return false;
    },
    chip: 'Shown at Apr 12, 2026, after the extension and the receipt'
  };
})();
