# 파랑새 배포 명세 — 행정망(망분리) 운영 + 시험 배포

작성 2026-10-06. 설계 근거는 `docs/ARCHITECTURE.md`. 도식: `docs/diagrams/architecture.pdf`(시스템 구성도, 생성: `build.py`), `docs/diagrams/deployment.html`(서버·버전·포트). 이 문서는 "어느 서버에 무엇을, 어떤 버전으로, 어떤 주기로" 올리는지를 정한다.

현재 구현 범위: 수집(파일 소스) → 망연계 번들 → 처리존 적재 → 공개 반출 → 공개존 적재 → 포털(아이디어 풀 목록·상세·API)까지 전 구간이 동작한다. 카드 추출(P1), 임베딩, 흔적 수집, 진단(P2), 시의성(P3), 공고 매칭, 검토 콘솔은 같은 번들·구역 구조 위에 단계로 추가한다(§6 표의 "예정" 항목).

---

## 1. 구역과 서버

| 구역 | 서버 | 역할 | 권장 사양 | 비고 |
|---|---|---|---|---|
| Z1 인터넷 수집존 | `z1-collect` | 외부 API·파일 수집, 팀명 마스킹, 번들 서명 | 2 vCPU / 4 GB / 100 GB | 인터넷망. 아웃바운드는 프록시 + 도메인 허용목록 |
| Z2 내부 처리존 | `z2-app` | importer·worker·publisher, 검토 콘솔(예정) | 8 vCPU / 32 GB / 200 GB | 인터넷 차단 |
| | `z2-db` | PostgreSQL 16 + pgvector (core) | 4 vCPU / 16 GB / 200 GB SSD | |
| | `z2-gpu` (예정) | vLLM(EXAONE) + BGE-M3 | GPU VRAM 80 GB급 1장 (EXAONE 30B급 bf16) 또는 48 GB급(양자화) | 모델 라이선스 확인 필요 |
| | `z2-backup` | 백업 저장 | 1 TB | 기관 백업 체계로 대체 가능 |
| Z3 DMZ 공개존 | `z3-web` | nginx(443), portal, importer, 임베딩(예정) | 4 vCPU / 8 GB / 50 GB | 인바운드 443만 |
| | `z3-db` | PostgreSQL 16 (publish) | 2 vCPU / 8 GB / 50 GB | DMZ 내부 DB 세그먼트 |

방화벽 정책표와 망연계 경로: `deploy/prod/firewall/README.md`.

## 2. 소프트웨어 스택

| 구분 | 선택 | 버전 | 선택 이유 |
|---|---|---|---|
| OS | Rocky Linux 9 (또는 RHEL 9) | 9.x | 공공기관 표준 계열, SELinux enforcing |
| 컨테이너 런타임 | Podman (rootless 아님, systemd 단위 관리) | RHEL 9 기본 | 데몬 없음, RHEL 기본 패키지라 내부망 반입이 쉬움. 이미지는 `podman load`로 반입 |
| 웹서버 / 리버스 프록시 | nginx | 1.26+ (RHEL AppStream) / 시험은 1.28-alpine | TLS 종료, 요청 제한, 보안 헤더, 메서드 제한. 설정 `deploy/prod/nginx/`, 공통 `deploy/nginx/` |
| WAF | 기관 표준 WAF(장비) | — | nginx 앞단. 파랑새 쪽 별도 구성 없음 |
| DB | PostgreSQL + pgvector | 16 / 0.8 | 벡터 검색(유사 아이디어·공고 매칭)을 DB 안에서 처리. 국산 DBMS는 벡터 확장이 없어 별도 벡터 DB가 필요해진다 |
| 웹 애플리케이션 | Next.js (standalone) on Node.js | 15.5 / 22 LTS | 공개 포털. 루프백 3000에서만 수신 |
| 파이프라인 | Python + psycopg 3 | 3.12 | 수집·적재·처리 공용 CLI `bluebird` |
| 번들 서명 | Ed25519 (`cryptography`) | — | 구역별 키. 운영 이관 시 기관 요구에 따라 검증필 암호모듈(KCMVP)로 교체 여부 확인 |
| LLM 서빙 (예정) | vLLM, OpenAI 호환 API | — | 처리존 내부 전용 |
| 임베딩 (예정) | BGE-M3 (MIT) | — | Z2·Z3 동일 모델 해시 |
| 스케줄러 | systemd timer | — | 실행 기록이 journald에 남고 `Persistent=true`로 누락 실행을 보정 |

## 3. 망분리 구조

```
인터넷 ──443──▶ [WAF] ─▶ z3-web(nginx → portal) ─▶ z3-db
                                  ▲ L2 망연계(파일)           │
                                  │                           ▼ L3 망연계(이의 제기, 예정)
z1-collect ──L1 망연계(파일)──▶ z2-app(importer/worker/publisher) ─▶ z2-db
   │                                   └─▶ z2-gpu (예정)
   └─443─▶ 허용 도메인 (프록시)
```

원칙

1. Z2는 인터넷과 연결되지 않는다. Z2→Z1 흐름도 없다. 수집에 필요한 질의는 Z1이 자기 원본에서 만든다.
2. 구역 간 이동은 망연계 솔루션을 통한 파일(번들)로만 한다. DB 복제나 API 호출로 구역을 넘지 않는다.
3. 번들 = `manifest.json`(테이블별 sha256·행 수) + `manifest.sig`(Ed25519) + `*.ndjson.gz`를 담은 tar 1개. 받는 쪽은 서명 → 해시 → 행 수 → 구성 파일 → 컬럼 순서로 검증하고, 하나라도 어긋나면 `quarantine/`으로 격리한다(종료코드 2). 같은 번들을 두 번 받아도 한 번만 적용된다.
4. 키 배치: Z1은 `z1.key`와 `z1.anon_secret`, Z2는 `z1.pub`와 `z2.key`, Z3는 `z2.pub`만 가진다. 개인키는 그 구역 밖으로 나가지 않는다.
5. Z2→Z3 반출은 컬럼 허용목록(`stages.PUBLISH_COLUMNS`) 방식이다. Z3 적재기도 같은 목록으로 다시 검사한다. `public_ok=false`인 소스(예: KIPRIS 벌크)는 반출 쿼리에서 제외된다.
6. 개인정보: 팀명은 Z1에서 본문 마스킹(○○)한 뒤 버리고, 원천 행 번호 대신 HMAC 익명 ID를 쓴다. Z2·Z3에는 팀명이 없다. 남는 것은 팀명 유형(`team_kind`)뿐이며, 이것도 Z3로는 반출하지 않는다.

망연계 솔루션 설정 요구사항(기관 솔루션에 맞춰 적용)

- L1: `z1-collect-*.tar`만 허용, 1개 최대 1 GB, 악성코드 검사 후 전달.
- L2: `z2-publish-*.tar`만 허용.
- 전송 중 파일은 `.part` 같은 임시 이름을 쓰다가 완료 후 이름을 바꾼다. 적재기는 이름이 `.`으로 시작하는 파일과 `.tar`가 아닌 파일을 무시한다.

## 4. DB

| DB | 위치 | 스키마 | 계정 | 권한 |
|---|---|---|---|---|
| `bluebird_core` | z2-db | `core` | `bluebird` | 소유자(마이그레이션·적재·처리) |
| | | | `bb_api` (backend-api, 마이그레이션 0008) | core 읽기 + 검토·공개 승인·이의 처리 열만 쓰기, NOSUPERUSER |
| | | | `bluebird_ro` | 백업·감사 조회 |
| `bluebird_publish` | z3-db | `publish` | `bluebird` | 소유자(스냅샷 교체) |
| | | | `bluebird_portal` | SELECT 전용 |

- 마이그레이션: `pipeline/bluebird/db/migrations/{core,publish}/NNNN_*.sql`. `bluebird migrate --target core|publish`로 적용하고 `public.schema_migrations`에 기록한다. 이 디렉터리가 스키마의 유일한 소유자다.
- 공개존 갱신 방식: 매번 전체 스냅샷을 하나의 트랜잭션 안에서 TRUNCATE→COPY로 교체한다. 그래서 포털은 갱신 도중에도 이전 스냅샷 또는 새 스냅샷만 보게 된다. 오래된 스냅샷이 늦게 도착하면 거부한다.
- 접속: `hostssl` + `scram-sha-256`, 허용 IP 고정(`deploy/prod/postgres/pg_hba.*.conf`).
- 로그: 접속·종료·DDL·1초 이상 쿼리를 기록한다(`deploy/prod/postgres/bluebird.conf`).

## 5. 데이터 소스와 수집 주기

| 소스 | 방식 | 주기 | 구현 |
|---|---|---|---|
| 창업경진대회 예선기관 수상작(2,190) | 파일 반입(seed) | 갱신 시(연 1회) | ✅ `awards_csv` |
| KIPRIS 공모전 아이디어 벌크(26,434) | 파일 반입 | 1회 | ✅ `kipris_idea_master` (내부 전용, 반출 안 됨) |
| 서울시 창업경진대회 수상작 2종, 과학관·농식품부·공공디자인 수상작 | data.go.kr 파일 | 주 1회 변경 확인(해시) | 예정 |
| KIPRISPlus 아이디어 DB(15006010) | data.go.kr 파일 | 1회 | 예정 (공개용 KIPRIS 소스) |
| K-Startup 사업공고 / 기업마당 | REST | 일 1회 | 예정 (공고 매칭·후속 지원 흔적) |
| 금융위 기업기본정보 → 국세청 사업자 상태 | REST | 최초 전수, 이후 월 1회 | 예정 (법인·사업자 흔적) |
| KIPRIS Plus 특허·상표 | REST | 최초 전수, 이후 월 1회 | 예정 |
| NAVER API HUB 뉴스·웹 | REST | 최초 전수(약 7천 질의), 이후 월 1회 | 예정 |
| 법제처 법령 | REST, 공포일 기간 | 주 1회 | 예정 (제도 정합성) |
| 정책브리핑 정책뉴스·보도자료 | REST, 기간 | 일 1회 | 예정 (정책 수요) |
| 공공데이터 개방목록 | 파일 | 월 1회 | 예정 (데이터 개방도) |

## 6. 실행 일정 (systemd timer)

| 시각(KST) | 서버 | 단계 | 상태 |
|---|---|---|---|
| 02:00 매일 | z1-collect | `collect` — 변경된 소스만 번들 생성 | ✅ |
| 30분마다 | z2-app | `import-core` — L1 수신함 적재 | ✅ |
| 03:00 매일 | z2-app | `extract`(P1) → `embed` 신규분 | 예정 |
| 일 03:30 | z2-app | `cluster` (주 1회) | 예정 |
| 04:00 매일 | z2-app | `trace-judge` → `diagnose`(P2) 신규 흔적분 | 예정 |
| 월 05:00 | z2-app | `score`(P3) (주 1회 + 개방 이벤트) | 예정 |
| 05:30 매일 | z2-app | `match` 신규 공고 | 예정 |
| 06:00 매일 | z2-app | `publish` — 공개 스냅샷 반출 | ✅ |
| 15분마다 | z3-web | `import-publish` — L2 수신함 적재 | ✅ |
| 01:00 매일 | z2-db, z3-db | `pg_dump` + WAL 보관 | 운영 구성 |

단위 파일: `deploy/prod/systemd/` (`bluebird-job@.service` 템플릿 + 단계별 timer, `bluebird-portal.service`).

번들 크기 실측(2026-10-06 시험): 수상작 2,190건 230 KB, KIPRIS 26,434건 10 MB, 공개 스냅샷 230 KB.

## 7. 운영·보안 항목

| 항목 | 내용 |
|---|---|
| 접속기록 | nginx access log, PostgreSQL 접속 로그, journald(단계 실행). 보관 기간은 기관 규정(개인정보 처리시스템 접속기록 기준)을 따른다 |
| 백업 | core: `pg_dump` 일 1회 + WAL 아카이브(PITR), 30일 보관. publish: core에서 다시 만들 수 있으므로 일 1회 덤프 7일 보관 |
| 감시 | `/healthz`(내부 대역만), `core.pipeline_run`(단계별 성공·실패·통계), `quarantine/` 파일 수 |
| 이미지 반입 | 인터넷망 CI 빌드 → `podman save` → 서명·해시 → 망연계 반입 → 검증 → `podman load`. 버전 태그 고정(`BB_VERSION`) |
| 비밀값 | `/etc/bluebird/*.env`, `/etc/bluebird/keys/` 0600 root. 저장소에는 `deploy/prod/env.example`만 |
| 웹 보안 | TLS 1.2/1.3, HSTS, CSP, X-Frame-Options DENY, 서버 버전 미노출, GET/HEAD/POST 외 405, 요청 제한(API 10 r/s, 페이지 30 r/s), 본문 64 KB 제한 |
| 컨테이너 | uid 10001, read-only 루트 파일시스템, tmpfs `/tmp` |
| 사전 절차 | 보안성 검토(운영기관), 웹 취약점 점검, 시큐어코딩 점검, 개인정보 영향 검토(팀명 처리 방식 §3-6 근거 제출), 민간 클라우드 사용 시 CSAP 확인 |

## 8. 시험 배포 (단일 호스트 재현)

`deploy/test/`가 운영 구조를 docker compose 하나로 재현한다.

| 운영 | 시험 |
|---|---|
| z1-collect 서버 | `collector` 컨테이너, `z1_net`(외부 통신 가능) |
| z2-app, z2-db | `worker`, `core-db`, `z2_net`(internal, 외부 차단) |
| z3-web, z3-db | `nginx`, `portal`, `importer`, `publish-db`, `z3_net`(internal) + `edge_net`(nginx만) |
| 망연계 L1·L2 | `mover-12`, `mover-23` (네트워크 없음, 양쪽 디렉터리만 마운트) |
| systemd timer | `run-cycle.sh` (같은 명령을 순서대로 1회 실행) |
| TLS 443 | HTTP 8080 |

실행

```bash
deploy/test/init.sh            # 키·.env·시드 준비 (reference/parangsae-src 사용)
cd deploy/test
docker compose --env-file .env build worker portal
./run-cycle.sh                 # 수집→망연계→적재→반출→망연계→적재→포털 기동
./verify.sh                    # 망분리·반출 통제·화면 검증
open http://localhost:8080/pool
docker compose --env-file .env down -v   # 정리
```

`verify.sh` 검증 항목 (2026-10-06 실행 결과 15/15 PASS)

- Z1 외부 통신 가능 / Z2·Z3 외부 통신 차단 / mover 네트워크 없음
- 공개존 아이디어 수 = 처리존의 공개 허용분(2,190 / 전체 28,624), 비공개 소스(KIPRIS 벌크 26,434) 미반출
- 공개존에 `team_kind`·`extra`·번들 추적 컬럼 없음, 포털 DB 계정 쓰기 불가
- `/pool`·`/ideas/{id}` 200, 없는 ID 404, DELETE 405, CSP 헤더, nginx 버전 미노출

추가로 수동 확인한 것: 변조 번들 격리(sha256 불일치 → `quarantine/`, 종료코드 2), 변경 없는 소스 재수집 생략, 동일 번들 재적재 시 갱신만 발생.

시험 환경 한정 완화: 런타임 디렉터리 권한을 `a+rwX`로 둔다(컨테이너 uid 10001과 호스트 사용자 불일치 때문). 운영에서는 `/srv/bluebird`를 10001 소유, 0700으로 둔다.

## 9. 이관 체크리스트

1. 운영기관과 확정: 서버 대역, 망연계 솔루션 종류·경로(L1·L2), WAF, 인증서, 백업 체계, 접속기록 보관 기간.
2. 서버 구성: Rocky/RHEL 9, Podman, nginx, PostgreSQL 16 + pgvector RPM(내부 저장소 미러).
3. 키 생성: 각 구역에서 `bluebird keygen --zone zN`을 실행하고, 공개키만 다음 구역으로 반입.
4. DB 생성 → `bluebird migrate` → 포털 계정 생성(`deploy/test/initdb/publish/00-roles.sh`와 같은 SQL).
5. systemd 단위 설치 → `systemctl enable --now bluebird-*.timer bluebird-portal.service`.
6. 1회 수동 주기 실행 → §8과 같은 항목을 운영 환경에서 점검.
