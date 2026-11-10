#!/usr/bin/env bash
# Rebuild every generated part of the design system from a clean checkout, in order.
# Output: generated cards in place under system/components/, plus build/ (gitignored):
#   build/screens.html   every screen in one clickable page (open it in a browser)
#   build/cards/<Card>.html   each card on its own, with the tokens and the stylesheet included
# Needs python3 and node. Thumbnails need Google Chrome ($CHROME) and sips; without them that step is skipped.
set -e
T="$(cd "$(dirname "$0")" && pwd)"; S="$(cd "$T/.." && pwd)"; R="$S/system"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"; export CHROME
cd "$S"
cards_with() { grep -l "<!-- /$1-scripts -->" "$R"/components/*/preview.html 2>/dev/null | xargs -n1 dirname | xargs -n1 basename | grep -v '^Walkthrough$' | tr '\n' ' '; }

echo "1. Report data and the evidence report"
python3 "$T/report_data.py"
python3 "$T/report/summary.py" "$R"
python3 "$T/report/gen_table.py" "$R"
python3 "$T/sections/gen.py" "$R"
python3 "$T/report/build_signoff_sources.py" 22
python3 "$T/report/normalize_heads.py" "$R" >/dev/null
python3 "$T/build_report.py" "$R"
python3 "$T/build_closeout.py" "$R"

echo "2. Cards built by generators"
python3 "$T/charges/gen.py"
python3 "$T/evidence/build.py"
python3 "$T/terms/build.py" >/dev/null
python3 "$T/problems/build_cards.py"
python3 "$T/thread/build_card.py"
python3 "$T/checklist/build.py"
python3 "$T/menus/build_card.py"

echo "3. Shared scripts into the cards that carry them"
python3 "$T/inline_viewer.py" "$R" $(cards_with viewer) | tail -1
python3 "$T/inline_pr6.py" "$R" $(cards_with pr6) | tail -1
python3 "$T/inline_layout.py" "$R" $(cards_with layout) | tail -1
python3 "$T/inline_menu.py" "$R" $(cards_with menu) | tail -1

echo "4. Thumbnails and the screen map (optional)"
if [[ -x "$CHROME" ]]; then
  "$T/thumbs.sh"
  if ls "$S"/build/shots/map/*.jpg >/dev/null 2>&1; then python3 "$T/map/build.py"; else echo "   no thumbnails, keeping the committed ScreenMap card"; fi
else
  echo "   Chrome not found at \$CHROME, skipping thumbnails; the ScreenMap card stays as committed and the screens page has blank thumbnails"
fi

echo "5. The Walkthrough card and the screens page"
python3 "$T/walk/build.py"
mkdir -p "$S/build/shots/walk"
python3 "$T/harness.py" "$R" "$S/build/shots/walk/w.html" Walkthrough light >/dev/null
if [[ -f "$S/build/shots/map/map-light.png" ]] || [[ -f "$S/build/shots/map/map.jpg" ]]; then :; elif [[ -x "$CHROME" ]] && command -v sips >/dev/null; then
  "$T/shoot.sh" ScreenMap light "t=light" "$S/build/shots/map/map-light.png" 1440 2660
  sips -c 900 1440 --cropOffset 0 0 "$S/build/shots/map/map-light.png" --out "$S/build/shots/map/mapcrop.png" >/dev/null
  sips -Z 560 -s format jpeg -s formatOptions 72 "$S/build/shots/map/mapcrop.png" --out "$S/build/shots/map/map.jpg" >/dev/null
fi
python3 "$T/walk/standalone.py"

echo "6. Every card on its own, in build/cards/"
mkdir -p "$S/build/cards"
for d in "$R"/components/*/; do
  c=$(basename "$d"); [[ "$c" == _src ]] && continue; [[ -f "$d/preview.html" ]] || continue
  python3 "$T/harness.py" "$R" "$S/build/cards/$c.html" "$c" light >/dev/null
done
echo "Done. Open build/screens.html in a browser."
