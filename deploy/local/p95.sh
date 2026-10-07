#!/usr/bin/env bash
# 화면2(주제·공고 넣기) pg_trgm 조회 p95 측정(G8 must 대체: < 300 ms).
# 포털 → 공개 DB 전 구간을 잰다. 초당 5건으로 보낸다.
# 사용: deploy/local/p95.sh [반복 수=8]  결과: .runtime/p95-<날짜>.txt
set -euo pipefail
cd "$(dirname "$0")/../.."
port="$(grep ^BB_PORTAL_PORT= .env | cut -d= -f2)"
rounds="${1:-8}"
out=".runtime/p95-$(date +%Y%m%d-%H%M%S).txt"
python3 - "$port" "$rounds" "$out" <<'PY'
import json, statistics, sys, time, urllib.parse, urllib.request
port, rounds, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
# 공모전 주제에서 흔한 낱말(짧은·긴·공고 제목형 섞음)
queries = ["대체조제", "만성질환 관리", "공공자전거", "미세먼지", "주차장 공유", "농산물 직거래", "관광 안내",
           "어린이 안전", "노인 돌봄 서비스", "전기차 충전소 위치", "반려동물", "부동산 실거래가", "날씨 기반 추천",
           "청년 창업 지원 공고", "의약품 안전 정보", "버스 도착 정보", "재난 대피소", "음식점 위생 등급",
           "에너지 절약", "장애인 이동 편의"]
lat, hits, errors = [], [], 0
url = f"http://localhost:{port}/api/v1/explore?q="
for _ in range(rounds):
    for q in queries:
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(url + urllib.parse.quote(q), timeout=10) as r:
                body = json.load(r)
            lat.append((time.perf_counter() - t0) * 1000)
            hits.append(len(body["ideas"]))
        except Exception as e:
            errors += 1
            print("error", q, e, file=sys.stderr)
        time.sleep(0.2)
lat.sort()
p = lambda k: lat[min(len(lat) - 1, int(round(k / 100 * len(lat) + 0.5)) - 1)]
res = {"requests": len(lat), "errors": errors, "p50_ms": round(p(50), 1), "p95_ms": round(p(95), 1),
       "p99_ms": round(p(99), 1), "max_ms": round(lat[-1], 1), "mean_hits": round(statistics.mean(hits), 1),
       "target_ms": 300, "pass": errors == 0 and p(95) < 300,
       "measured_at": time.strftime("%Y-%m-%d %H:%M:%S %z"), "path": "portal→publish DB (/api/v1/explore)"}
print(json.dumps(res, ensure_ascii=False))
open(out, "w").write(json.dumps(res, ensure_ascii=False, indent=1) + "\n")
sys.exit(0 if res["pass"] else 1)
PY
echo "[p95] saved $out"
