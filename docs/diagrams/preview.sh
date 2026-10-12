#!/usr/bin/env bash
# 표준 Python만으로 구성도 생성·미리보기. 브라우저에서 출력된 주소를 연다.
set -euo pipefail
root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
python3 "$root/build.py"
printf '구성도: http://127.0.0.1:%s/architecture.html\n' "${PORT:-8765}"
exec python3 -m http.server "${PORT:-8765}" --bind 127.0.0.1 --directory "$root"
