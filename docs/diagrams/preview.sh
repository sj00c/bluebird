#!/usr/bin/env bash
# build.py 저장 → architecture.html/pdf 재생성 → 터미널 칸(cmux/Ghostty)에 그림 표시
set -u
cd "$(dirname "$0")"
OUT=/tmp/bb-preview
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
mkdir -p "$OUT"
(
  last=""
  while true; do
    cur=$(stat -f %m build.py)
    if [[ "$cur" != "$last" ]]; then
      last="$cur"
      python3 build.py >/dev/null 2>&1
      "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 --window-size=1648,888 \
        --virtual-time-budget=3000 --screenshot="$OUT/tmp.png" "file://$PWD/architecture.html" >/dev/null 2>&1 \
        && mv "$OUT/tmp.png" "$OUT/page-1.png"
    fi
    sleep 1
  done
) &
trap 'kill $! 2>/dev/null' EXIT
sleep 3
/usr/local/bin/python3 /Users/sj/dev/gen_resume/applications/_shared/cv/view_pages.py "$OUT"
