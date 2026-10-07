# 방화벽 정책표 (운영 예시 대역)

| 구역 | 서버 | 예시 IP |
|---|---|---|
| Z1 인터넷 수집존 | z1-collect | 203.0.113.0/28 대역 내부 (인터넷망 업무 세그먼트) |
| 망연계 | 망연계 솔루션(송·수신 에이전트) | 기관 표준 |
| Z2 내부 처리존 | z2-app 10.20.10.11 · z2-db 10.20.10.21 · z2-gpu 10.20.10.41 · z2-backup 10.20.10.31 | 10.20.10.0/24 |
| Z3 DMZ | z3-web 172.16.30.11 · z3-db 172.16.30.21 | 172.16.30.0/24 |

| # | 출발 | 도착 | 포트 | 용도 |
|---|---|---|---|---|
| F1 | 인터넷 | z3-web | 443/tcp (80→443 리다이렉트) | 공개 포털 |
| F2 | z3-web | z3-db | 5432/tcp | importer·portal |
| F3 | z1-collect | 허용 도메인(data.go.kr, plus.kipris.or.kr, open.law.go.kr, k-startup.go.kr, bizinfo.go.kr, NAVER API HUB, 디지털융합플랫폼) | 443/tcp | 수집 (프록시 경유 + 도메인 허용목록) |
| F4 | z2-app | z2-db | 5432/tcp | worker·console |
| F5 | z2-app | z2-gpu | 8000/tcp | LLM(vLLM)·임베딩 |
| F6 | 운영자 PC(업무망) | z2-app | 443/tcp | console(검토 화면) |
| F7 | 관리망 | 전 서버 | 22/tcp | 관리 (접근통제 솔루션 경유) |
| — | z2-* | 인터넷 | 전체 | **차단** |
| — | z3-* | z2-* | 전체 | **차단** (망연계로만) |
| — | z2-* | z3-* | 전체 | **차단** (망연계로만) |
| — | z1-collect | z2-*, z3-* | 전체 | **차단** (망연계로만) |
| — | z3-web | 인터넷 | 전체 | **차단** (응답 외 신규 아웃바운드 없음) |

망연계 경로(파일 단방향)

| 경로 | 송신 폴더 | 수신 폴더 | 허용 파일 |
|---|---|---|---|
| L1 Z1→Z2 | z1-collect:/srv/bluebird/xfer/out-to-z2 | z2-app:/srv/bluebird/xfer/in-from-z1 | `z1-collect-*.tar` |
| L2 Z2→Z3 | z2-app:/srv/bluebird/xfer/out-to-z3 | z3-web:/srv/bluebird/xfer/in-from-z2 | `z2-publish-*.tar` |
| L3 Z3→Z2 | z3-web:/srv/bluebird/xfer/out-to-z2 | z2-app:/srv/bluebird/xfer/in-from-z3 | `z3-ticket-*.tar` (이의 제기 구현 시) |
