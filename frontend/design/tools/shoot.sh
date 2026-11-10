#!/usr/bin/env bash
# usage: shoot.sh Comp theme "hash" out.png [W H]
S="$(cd "$(dirname "$0")/../" && pwd)"  # frontend/design
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
mkdir -p "$S/build/shots/ag"
html=$S/build/shots/ag/$1-$2.html
python3 $S/tools/harness.py $S/system $html $1 $2 >/dev/null
perl -e "alarm 30; exec @ARGV" "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 --window-size=${5:-1440},${6:-1000} --virtual-time-budget=${7:-4000} --screenshot=$4 "file://$html#$3" >/dev/null 2>&1
