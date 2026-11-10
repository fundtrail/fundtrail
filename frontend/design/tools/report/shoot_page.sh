#!/usr/bin/env bash
# usage: shoot_page.sh theme N out.png [signed]   renders one report page alone (no scrolling involved)
S="$(cd "$(dirname "$0")/../../" && pwd)"  # frontend/design
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
mkdir -p "$S/build/shots/closeout"
src=$S/build/shots/closeout/all-full-$1.html; one=$S/build/shots/closeout/all-one-$1-$2${4:+-signed}.html
python3 $S/tools/harness.py $S/system $src EvidenceReport $1 >/dev/null
python3 - "$src" "$one" "$2" "$4" <<'PY'
import sys, re
s = open(sys.argv[1]).read(); n = sys.argv[3]
pages = re.findall(r'<section class="ft-rpage[^"]*" id="rp-(\d+)".*?</section>\n?', s, re.S)
keep = re.search(r'(<section class="ft-rpage[^"]*" id="rp-' + n + r'".*?</footer></section>)', s, re.S).group(1)
s = re.sub(r'(<main[^>]*>).*?(</main>)', lambda m: m.group(1) + keep + m.group(2), s, flags=re.S)
if sys.argv[4] == 'signed': s = s.replace('<html lang="en"', '<html lang="en" class="is-signed"', 1)
open(sys.argv[2], 'w').write(s)
PY
perl -e "alarm 30; exec @ARGV" "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 --window-size=900,1110 --virtual-time-budget=3000 --screenshot=$3 "file://$one" >/dev/null 2>&1
