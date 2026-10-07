# 파랑새 배포 명세 — 운영 배포 + 시험 배포

갱신 2026-10-07. 설계 근거는 `docs/ARCHITECTURE.md`. 도식: `docs/diagrams/architecture.html`(PDF: `architecture.pdf`). 이 문서는 "어느 호스트에 무엇을, 어떤 주기로" 올리는지를 정한다.

핵심: **업무망으로 들어오는 연결은 없다.** 모든 연결은 업무망이 연다.

---

## 1. 호스트

| 구역 | 호스트(예시 IP) | 올리는 것 |
|---|---|---|
| DMZ | dmz-web (172.16.30.11) | Nginx(WAF 뒤), portal |
| DMZ | dmz-db (172.16.30.21) | 공개용 DB (PostgreSQL, 스키마 `publish` `meta` `inbox`) |
| DMZ | dmz-proxy (172.16.30.31) | 포워드 프록시(Squid) |
| 업무망 | biz-app (10.20.10.11) | backend-jobs(systemd 타이머), backend-api, 콘솔, console-gw |
| 업무망 | biz-db (10.20.10.21) | core DB (PostgreSQL + pgvector, 스키마 `core`) |
| 업무망 | biz-backup (10.20.10.31) | 백업 저장 |

DMZ의 세 호스트는 작은 규모에서는 한 호스트에 합쳐도 된다(포트와 접속 계정 규칙은 같다). 사양은 운영기관과 실측 후 정한다. 방화벽: `deploy/prod/firewall/README.md`.

## 2. 소프트웨어

| 구분 | 선택 | 비고 |
|---|---|---|
| OS | Rocky Linux 9 (또는 RHEL 9) | SELinux enforcing |
| 컨테이너 | Podman, systemd 단위로 관리 | 이미지는 `podman load`로 반입 |
| 웹서버 | nginx 1.26+ (시험은 1.28-alpine) | TLS 종료, 요청 제한, 보안 헤더. 설정 `deploy/prod/nginx/`, 공통 `deploy/nginx/` |
| WAF | 기관 표준 WAF 장비 | nginx 앞단 |
| DB | PostgreSQL 16 (+ pgvector, pg_trgm) | core·공개용 모두 같은 이미지 계열 |
| 포털·콘솔 | Next.js standalone, Node.js 22 | |
| 파이프라인·API | Python 3.12, FastAPI | 이미지 `bluebird/pipeline` 하나 |
| 포워드 프록시 | Squid 6.13 | 설정 `deploy/test/proxy/squid.conf`(운영도 같은 허용목록) |
| 스케줄러 | systemd timer | 실행 기록은 journald, `Persistent=true`로 누락 실행 보정 |

## 3. 방화벽 4겹

`deploy/prod/firewall/README.md`와 같은 표다.

| 겹 | 출발 → 도착 | 내용 |
|---|---|---|
| ① | 사용자 → WAF → dmz-web Nginx | 443/tcp만. 공개 포털로 가는 유일한 길 |
| ② | 업무망 biz-app → dmz-db | 5432/tcp. 공개본 밀어넣기(`bb_publisher`), 이의 가져오기·삭제(`bb_inbox_reader`). 업무망이 연다 |
| ③ | 업무망 biz-app → dmz-proxy | 3128/tcp. 프록시는 허용 도메인의 443/tcp로만 나간다(`.data.go.kr .law.go.kr .kipris.or.kr .k-startup.go.kr .bizinfo.go.kr` 등) |
| ④ | 관리자 PC → biz-app console-gw | 443/tcp. 관리자 콘솔로 가는 유일한 길 |

차단: DMZ → 업무망 전부, 인터넷 → 업무망, 업무망 → 인터넷(프록시 제외), DMZ 웹·DB → 인터넷.

## 4. 데이터베이스

| DB | 위치 | 계정 | 권한 |
|---|---|---|---|
| `bluebird_core` | biz-db | `bluebird` | 소유자(마이그레이션·적재·처리). backend-jobs가 사용 |
| | | `bb_api` | backend-api 전용 최소 권한. 읽기 + 검토·승인·이의 처리 열만 쓰기 (마이그레이션 0008) |
| `bluebird_publish` | dmz-db | `bb_migrator` | 스키마 변경(필요할 때만) |
| | | `bb_publisher` | 공개본 교체(push) |
| | | `bb_inbox_reader` | inbox 읽기·삭제만 |
| | | `bb_portal` | publish 읽기 + inbox INSERT |

`pg_hba` 요약 (`deploy/prod/postgres/`)

- core: `hostssl`, SCRAM. `bluebird`·`bb_api`는 biz-app에서만. 그 밖은 reject. DMZ 대역은 허용하지 않는다.
- 공개용 DB: `bb_portal`은 dmz-web에서, `bb_publisher`·`bb_inbox_reader`·`bb_migrator`는 업무망 biz-app에서만. 슈퍼유저는 원격 로그인 불가.
- 마이그레이션: `pipeline/bluebird/db/migrations/{core,publish}/`. `bluebird migrate --target core|publish`로 적용한다.
- `bb_api`는 마이그레이션이 NOLOGIN으로 만든다. 배포 때 한 번 `ALTER ROLE bb_api LOGIN PASSWORD :'pw'`를 psql 변수(stdin)로 실행한다. 새 core 표를 만드는 마이그레이션은 `bb_api` 권한을 같이 정한다.
- 공개용 DB 갱신: 새 스키마를 만들어 이름을 바꾸는 방식이라 포털은 이전 또는 새 스냅샷만 본다.
- 로그: 접속·종료·DDL·1초 이상 쿼리를 기록한다(`deploy/prod/postgres/bluebird.conf`).

## 5. nginx와 WAF (dmz-web)

`deploy/prod/nginx/bluebird.conf`. TLS 1.2/1.3, HSTS, 80→443 리다이렉트. 공통 location·보안 헤더는 `deploy/nginx/bluebird-common.conf`, 프록시 헤더는 `bluebird-proxy.conf`(시험과 같은 파일)다.

**WAF 뒤 접속자 IP**: nginx 앞에 WAF가 있어서 그대로 두면 모든 요청이 WAF 주소로 보인다. 요청 제한과 로그가 WAF 한 곳으로 뭉치므로 IP를 복원한다.

```nginx
set_real_ip_from 192.0.2.0/24;   # 기관 WAF의 출발 대역으로 바꾼다 (예시 값)
real_ip_header X-Forwarded-For;
real_ip_recursive on;
```

`set_real_ip_from`에는 WAF 대역만 넣는다. 그 밖에서 온 `X-Forwarded-For`는 믿지 않는다. 배포 때 WAF 대역을 운영기관에 받아 바꾼다.

요청 제한: API 10 r/s, 화면 30 r/s, 이의 제기 접수 IP당 분당 5건. 본문 64 KB 제한, GET/HEAD/POST 외 405, 서버 버전 미노출. `/healthz`는 내부 대역에서만.

## 6. 실행 일정 (systemd, 업무망 biz-app)

작업은 `bluebird-job@<이름>.service` 템플릿 하나로 실행한다. 명령은 `/etc/bluebird/<이름>.env`의 `BB_JOB_ARGS`로 정한다.

| 타이머 | 시각(KST) | 명령 |
|---|---|---|
| `bluebird-ingest.timer` | 매일 02:00 | `bluebird ingest` |
| `bluebird-cards.timer` | 매일 02:30 | `bluebird cards` (새 아이디어 카드) |
| `bluebird-signals.timer` | 매주 월 03:00 | `bluebird signals catalog-fetch --out-dir /srv/bluebird/signals` |
| `bluebird-publish.timer` | 매일 06:00 | `bluebird publish` (승인분 → 공개용 DB) |
| `bluebird-pull-objections.timer` | 10분마다 | `bluebird objections pull` (inbox 가져오기 후 삭제) |

상시 실행: `bluebird-api.service`(업무망 호스트, 루프백 8000), `bluebird-console.service`(루프백 3001, 앞단 console-gw), dmz-web의 `bluebird-portal.service`(루프백 3000). 루프백 수신 주소는 단위 파일이 `-e`로 고정한다(env 파일로 바꿀 수 없음). console-gw는 `deploy/prod/nginx/console-gw.conf`(443, 관리자 단말 대역만 allow, 그 밖 403)로 biz-app의 nginx에 올린다.

카드 만들기는 타이머(02:30)가 한다. 흔적·진단·바뀐 것 입력, 검토 승인은 콘솔과 `bluebird` 명령으로 사람이 진행한다. 단위 파일은 `deploy/prod/systemd/`.

## 7. 환경변수 (`deploy/prod/env.example`)

`/etc/bluebird/*.env`, 0600 root. 값에 따옴표를 쓰지 않는다. 저장소에는 예시만 둔다.

| 변수 | 쓰는 곳 | 뜻 |
|---|---|---|
| `BB_VERSION` | 공통 | 이미지 버전 태그(고정) |
| `BB_JOB_ARGS` | 작업별 env | 이미지에 넘기는 명령 |
| `BB_DSN` | backend-jobs, backend-api | core DB 접속. backend-api는 `bb_api` |
| `BB_SOURCES`, `BB_SEED_DIR`, `BB_SIGNAL_DIR` | backend-jobs | 소스 설정, 시드 파일, 신호 저장 폴더 |
| `BB_ANON_SECRET` | backend-jobs | 익명 ID 비밀키(백업 대상, 바꾸면 모든 ID가 바뀜) |
| `BLUEBIRD_EGRESS_PROXY` | backend-jobs | DMZ 포워드 프록시 주소 |
| `BB_PUBLISH_DSN` | publish | 공개용 DB 밀어넣기 (`bb_publisher`) |
| `BB_PUBLISH_MIGRATOR_DSN` | migrate | 공개용 DB 스키마 변경 (`bb_migrator`) |
| `BB_INBOX_DSN` | pull-objections | 이의 가져오기·삭제 (`bb_inbox_reader`) |
| `DATA_GO_KR_KEY`, `LAW_OC`, `BIZINFO_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `KIPRIS_PLUS_KEY` | backend-jobs | 외부 API 키. 비우면 그 소스는 건너뛰고 사람 경로로 간다 |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | backend-jobs | 상용 LLM. 둘 다 비면 규칙·사람 경로만 동작 |
| `BB_API_USERS` | backend-api | 토큰 sha256 해시 파일(`console_users.json`) |
| `BB_API_URL` | 콘솔 | backend-api 주소 |
| `PORTAL_DATABASE_URL` | portal | 공개용 DB 접속 (`bb_portal`) |

## 8. 운영·보안 항목

| 항목 | 내용 |
|---|---|
| 접속기록 | nginx access log, PostgreSQL 접속 로그, journald, Squid 접근 로그, `core.egress_call`. 보관 기간은 기관 규정을 따른다 |
| 백업 | core: `pg_dump` 일 1회 + WAL 아카이브(PITR). 공개용 DB는 core에서 다시 만들 수 있으므로 덤프만 |
| 감시 | `/healthz`(내부 대역), `core.pipeline_run`, `bluebird sources check`, `bluebird kpi report` |
| 이미지 반입 | 인터넷망 CI 빌드 → `podman save` → 서명·해시 → 기관 반입 절차 → 검증 → `podman load` |
| 비밀값 | `/etc/bluebird/*.env`, `/etc/bluebird/keys/` 0600 root |
| 컨테이너 | uid 10001, read-only 루트, tmpfs `/tmp` |
| 콘솔 접근 | 토큰 원문은 사람에게 전달, 서버에는 sha256만. console-gw는 관리자 단말에서만 접근 |
| 사전 절차 | 보안성 검토, 웹 취약점·시큐어코딩 점검, 개인정보 영향 검토(이름 익명화 방식 근거 제출), 민간 클라우드 사용 시 CSAP 확인 |

## 9. 테스트 배포 (단일 호스트 재현)

`deploy/test/compose.yaml`이 같은 구조를 한 호스트에서 재현한다.

| 운영 | 시험 |
|---|---|
| dmz-web | `nginx`(HTTP 8080), `portal` — `edge_net`, `dmz_net` |
| dmz-db | `publish-db` — `dmz_net`, `push_net` |
| dmz-proxy | `proxy`(Squid) — `egress_net`, `inet_net` |
| biz-db | `core-db` — `biz_net` |
| biz-app | `backend-jobs`(`docker compose run`), `backend-api`, `console` — `biz_net`, `push_net`, `egress_net`, `console_net` |
| console-gw | `console-gw` — `console_net`, `admin_net`, 호스트 `127.0.0.1:8090` |
| systemd timer | `run-cycle.sh` (같은 명령을 순서대로 1회 실행) |

`dmz_net`, `biz_net`, `console_net` 등은 internal이라 외부 연결이 없다. DMZ 컨테이너는 `biz_net`에 붙지 않는다.

실행

```bash
cd deploy/test
./init.sh          # 키·.env·시드·콘솔 토큰 준비 (reference/parangsae-src 사용)
./run-cycle.sh     # 마이그레이션 → ingest → cards → sources check → 신호 → 이의 pull → publish → 포털·콘솔 기동
./verify.sh        # 망 구성·반출 통제·깔때기·콘솔·이의 왕복·화면 검증
./p95.sh           # 화면2 주제·공고 검색 p95 측정 (결과 .runtime/p95-<날짜>.txt)
```

- 공개 화면: `http://localhost:8080/`
- 콘솔: `http://127.0.0.1:8090/` (이 호스트에서만). 로그인 토큰은 `deploy/test/.runtime/console_tokens`에 사람별로 한 줄씩(`reviewer1`, `coder_a1`, `coder_b1`, `expert1`, `auditor1`). 서버(backend-api)에는 해시 파일만 들어가고, 토큰 원문은 어떤 컨테이너에도 마운트되지 않는다.
- 정리: `docker compose --env-file .env down -v`

시험 환경 한정 완화: 런타임 디렉터리 권한을 `a+rwX`로 둔다(컨테이너 uid와 호스트 사용자 불일치). 운영에서는 `/srv/bluebird`를 10001 소유, 0700으로 둔다.

## 10. 이관 체크리스트

1. 운영기관과 확정: 서버 대역, WAF 출발 대역(§5), 인증서, 백업 체계, 접속기록 보관 기간, N2SF 등급.
2. 서버 구성: Rocky/RHEL 9, Podman, nginx, PostgreSQL 16 + pgvector(내부 저장소 미러).
3. 방화벽 4겹(§3)을 적용하고, DMZ → 업무망이 막혀 있는지 확인.
4. DB 생성 → `bluebird migrate --target core` / `--target publish` → 공개용 DB 역할 생성(`deploy/test/initdb/publish/00-roles.sh`와 같은 SQL) → `bb_api` 로그인 비밀번호.
5. 익명화 비밀키(`BB_ANON_SECRET`) 생성·백업. 콘솔 토큰 발급(해시만 서버에).
6. 환경 파일 배치(§7) → systemd 단위 설치 → `systemctl enable --now bluebird-*.timer bluebird-api.service bluebird-console.service`(업무망), `bluebird-portal.service`(DMZ).
7. 1회 수동 주기 실행 후 `bluebird sources check`, `bluebird kpi report`로 점검.
