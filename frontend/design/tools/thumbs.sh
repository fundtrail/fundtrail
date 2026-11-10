#!/usr/bin/env bash
# Screenshot each screen and shrink it to a thumbnail in build/shots/map/, for the screen map and the screens page.
# Needs Google Chrome (set $CHROME to its binary if it isn't in the default macOS place) and sips (macOS) to make the JPEGs.
T="$(cd "$(dirname "$0")" && pwd)"; S="$(cd "$T/.." && pwd)"; O="$S/build/shots/map"
mkdir -p "$O"
shot() { "$T/shoot.sh" "$1" light "$2&t=light" "$O/$3.png" 1440 900; }
shot SignIn "" signin & shot SignIn "state=setup&step=1" setup & shot Workspace "" home & shot WorkspaceMenu "open=workspace" menu &
shot AddGrant "step=1" ag1 & shot AddGrant "step=2" ag2 & wait
shot AddGrant "step=3&up=1" ag3 & shot AddGrant "step=4&ev=1" ag4 & shot Demo "" grant & shot Demo "s=2" confirm & shot Demo "sel=L-1019" answer & wait
shot Demo "sel=L-1010" split & shot Demo "v=F1" viewer & shot Closeout "" closeout & shot Charges "" charges & shot Evidence "" evidence & shot GrantTerms "" terms & wait
"$T/report/shoot_page.sh" light 1 "$O/report.png"
if command -v sips >/dev/null; then
  for f in "$O"/*.png; do sips -Z 560 -s format jpeg -s formatOptions 72 "$f" --out "${f%.png}.jpg" >/dev/null; done
else
  echo "thumbs.sh: sips not found (macOS only), so the PNGs in $O were not turned into thumbnails" >&2
fi
