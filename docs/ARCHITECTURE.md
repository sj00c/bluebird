# 파랑새(Bluebird) 배포 아키텍처 설계 v1.0 — 최종 구조(DMZ·업무망)

갱신 2026-10-07. 입력: 예선 제출 기획서(`reference/parangsae-src/04_deck_build/output/submitted_proposal_prelim_capital_parangsae.pdf`), 인수인계 패키지(`reference/parangsae-src/`).

---

## 0. 출발점

### 0.1 인수인계 패키지 실사

배포 가능한 코드는 없다. 화면은 정적 HTML 목업 2장(예시 수치), 아키텍처는 그림, 파이프라인은 `pplx_sdk`에 묶인 50건 파일럿 스크립트다. 재사용 대상은 다음뿐이다.

- KIPRIS 벌크 파싱 규칙(CP949, `¶` 구분자, `<br />`, `#N/A`) — `02_kipris_bulk/load_kipris_contest.py`
- 흔적 검색 질의 생성 규칙(`product_name`, `clean_team`, `masked`)과 판정 프롬프트 — `03_pilot/step1·step2`
- 검수 완료 골드셋 50건 — `03_pilot/pilot_result_final.csv`
- 코드북 T·D·R·M·C·O·U 정의와 이론 배경 — 기획서 13쪽, `07_pitch/stall_cause_codebook_7_theory.md`
- 데이터 소스·API 접근조건 조사 — `06_research/datasets.md`

### 0.2 기획서에서 약속한 것 (설계 요구사항으로 고정)

| 구분 | 기획서 내용 | 쪽 |
|---|---|---|
| 핵심 기능 | ① 아이디어 풀 DB(3축 태그·군집·유사 묶음) ② 정체 원인 진단(흔적 4종 → 7코드) ③ 시의성 재평가(S 0~5) ④ 재조명 매칭·알림 | 3, 12 |
| 흔적 4종 | 뉴스·웹 / 법인·사업자 / 특허·상표 / 후속 지원사업 선정 | 12, 17 |
| 시의성 S | 기술 준비도·데이터 개방도·제도 정합성·정책 수요 4항목 가중평균. 초기 가중치 0.25 균등 → 멘토링 의견으로 조정. S≥4.0 지금 가능 / 3.0~3.9 조건부(해소 조건 명시) / <3.0 보류. 자료 없는 항목은 점수 미부여·평균에서 제외 | 14 |
| 프롬프트 | P1 카드 추출(title, problem, solution, target_user, required_data[], required_tech[], domain 9종 중 1, year, source_url, 추정 금지) / P2 원인 분류(primary, secondary≤1, confidence 0~1, rationale 2문장, evidence_ids[], 증거 없으면 U) / P3 시의성(항목별 0~5 + 근거 URL ≥1, 자료 없으면 판단 불가, 달라진 점 ≤3) | 20 |
| 신뢰성 | 표본 100건 2인 독립 코딩 κ≥0.7 후 채택 / 모든 판정에 근거 링크·수집일 / AI는 후보·근거까지, 최종 판정·공개는 담당자 확인 / 원문 변형 금지 / 이용자 이의 제기·정정 기능 | 10 |
| 데이터 원칙 | 수상자 성명·소속은 적재 단계에서 삭제, 아이디어 단위 익명 ID / 상업적 이용 금지·변경 금지 데이터 제외 / 빅카인즈 미사용 / 네이버는 API HUB / 디지털융합플랫폼 경유 우선 | 18 |
| 사용자 | 주최기관 담당자, 참가자(예비창업자·학생·직장인), 정책 기획자 | 11 |
| 정량 목표(’26.12) | 카드 1만 건+ / 진단 표본 100건 κ≥0.7 / 재발굴 후보 20건 전문가 검토 후 공개 / 공고 매칭 실사용 시연 / 유사 아이디어 조회 1초 내 / 근거 링크 100% | 15, 22, 23 |
| MVP 단계 | 1단계(~9월) 시드 적재·카드 추출·군집·진단 카드 화면 / 2단계(10~11월) 흔적 API·원인 분류·κ 검증·시의성 / 3단계(12월) 공고 매칭·알림·주최기관 모드·Top 20 공개 | 15 |

**현황 차이**: 기획서상 1단계(~9월)는 완료 상태여야 하지만 실제로는 목업만 있다. 10~11월에 1·2단계를 함께 진행해야 한다(§9).

### 0.3 기획서와 실데이터의 불일치 (설계에 반영)

1. **"3.8만 행"은 아이디어 수가 아니다.** KIPRIS 데이터사전 기준 분석 단위는 26,434건(1979~2014, 학생 발명 위주)이고, 2층 창업경진대회 수상작은 2,190 + 70건. 화면 수치는 DB 실측값만 쓴다. 목표인 "카드 1만 건+"는 달성 가능하다.
2. **흔적 판정은 5클래스다.** 파일럿 검수본 기준 `realized / pivot / similar_unlinked / award_only / none`(6/4/3/14/23). 이와 별도로 원인 코드(P2)는 `realized`가 아닌 건에만 부여한다.
3. **KIPRIS 벌크 TXT는 약관상 팀 내부 전용이다.** 공개 노출은 공공데이터포털 `15006010` 파일을 기준으로 한다.
4. **Supabase·RAGFlow·Superset**(기획서 19, 21쪽)은 망분리 환경에서 쓸 수 없거나 불필요하다. 자체 PostgreSQL+pgvector로 대체한다(§2).
5. **익명화와 흔적 검색이 충돌한다.** 흔적 검색에는 팀명이 필요한데, 기획서는 "적재 단계에서 삭제"로 약속했다. → 팀 이름과 사람 이름은 적재 때 지우고 익명 ID만 남긴다(§3.1). 흔적 검색은 아이템명으로 한다. 약속을 지키면서 검색도 가능하다.

---

## 1. 망분리 전제

공공포털로 운영하므로 공공기관 망분리 기준을 따른다.

- **기본 모델**: 인터넷 | DMZ | 내부 업무망 3구역. 업무망과 인터넷을 직접 잇지 않고, DMZ를 역할별로 둘로 나눈다.
  - **누가 쓰느냐로 위치를 정한다**: 국민(일반 이용자)이 쓰는 화면은 인터넷 쪽 DMZ에, 직원만 쓰는 검토·승인 콘솔은 업무망 안에 둔다. 운영기관이 정부기관이면 업무망 자리가 행정망이 된다.
  - **DMZ ① 서비스**: 국민 → 기관 홈페이지 메뉴 → 파랑새 화면(nginx) → DMZ 공개용 DB(읽기 전용). 국민 요청은 DMZ 안에서 끝나고 업무망은 밖에서 들어오는 요청을 받지 않는다. 업무망은 담당자가 승인한 자료만 공개용 DB로 한 방향 반영하고, 이의 제기는 DMZ에 쌓인 것을 업무망이 가져간다.
  - **DMZ ② 외부 연계**: 업무망 처리 서버의 외부 호출(공공 데이터 API, 상용 AI API)은 모두 이 구역의 포워드 프록시를 거친다. 허용 도메인만 나가고 모든 호출을 기록한다.
- **데이터 등급**: 국가망보안체계(N2SF)의 C/S/O 분류를 기준으로 삼는다. 파랑새가 다루는 데이터는 대부분 공개 데이터(O)이고, 수상팀명처럼 개인 식별 가능성이 있는 항목과 이용자 제출 정보(이의 제기, 알림 구독 이메일)만 S급으로 본다. C급은 없다. **최종 등급과 적용 체계는 운영기관 보안담당과 확정해야 한다.**
- **클라우드**: 민간 클라우드에 올리면 CSAP 인증 등급을 확인해야 한다. 모두의 AI 실험실 클라우드는 대회 시연용이고, 운영기관 이관 시 대상 인프라는 따로 정한다.
- **상용 Frontier 모델 사용**: 진단 품질 때문에 OpenAI·Anthropic API를 쓴다. 외부로 보내는 자료는 N2SF 등급상 외부 반출이 허용된 것(O급, 또는 기관이 허용한 범위)만이며, 처리 서버가 보내기 전에 등급을 검사해 막는다. 경로는 DMZ ② 프록시 하나뿐이다.

> 2026-10-07 최종 구조: 업무망은 밖에서 들어오는 연결을 받지 않는다. 업무망이 직접 연결을 열어 공개용 DB로 승인분을 밀어 넣고(한 방향), DMZ에 쌓인 이의 제기를 가져온 뒤 지운다. 인터넷으로 나가는 길은 DMZ 포워드 프록시 하나다. 기준 도식은 `docs/diagrams/architecture.html`(PDF: `architecture.pdf`)이다.

### 핵심 원칙

1. **처리는 업무망에서, 노출은 DMZ ①에서, 외부 호출은 DMZ ② 프록시로만 한다.**
2. **업무망에서 밖으로 나가는 길은 DMZ ② 프록시 하나다.** 허용 도메인(공공 데이터 API, 상용 AI API)만 열고, 외부 반출이 허용되지 않은 등급의 자료는 AI 호출에 넣지 않는다.
3. **DMZ에는 공개 승인된 데이터만 반출한다.** 반출은 컬럼 허용목록 방식이고, 사람 승인이 반출 조건이다. 이것으로 기획서의 "최종 판정·공개는 담당자 확인"을 구조적으로 보장한다.
4. **연결은 업무망이 연다.** 업무망은 들어오는 연결이 0개다. 공개용 DB로 밀어 넣기(push)와 이의 제기 가져오기(pull)는 모두 업무망이 먼저 연결한다. DMZ에서 업무망으로 가는 연결은 전부 막는다.

---

## 2. 구역 구성

```
 사용자 Zone                DMZ                                       업무망
 (시민·참가자)     ┌─────────────────────────────┐          ┌────────────────────────────────────┐
                   │ WAF → Nginx → portal        │          │ backend-jobs (python bluebird CLI) │
 브라우저 ───────▶ │            └▶ 공개용 DB ◀──┼── 밀어넣기 ─┤   수집·카드·진단·검토·공개          │
                   │               (publish·meta │  (업무망이 연결) │ backend-api (FastAPI)              │
                   │                ·inbox)  ────┼── 가져오고 삭제 ─▶ 콘솔 (Next.js) ← console-gw ← 관리자 PC │
                   │                             │          │ core DB (PostgreSQL + pgvector)    │
                   │ 포워드 프록시 (Squid) ◀─────┼── 외부 호출 ─┤                                    │
                   └──────────┬──────────────────┘          └────────────────────────────────────┘
                              ▼
                   허용 도메인 + 상용 AI (인터넷)
```

국민 요청은 DMZ에서 끝난다. 업무망은 밖에서 들어오는 연결을 하나도 받지 않는다. 업무망이 먼저 연결을 열고, 그 방향만 허용한다.

| 구역 | 구성 | 하는 일 |
|---|---|---|
| 사용자 Zone | 시민·참가자 브라우저 | DMZ의 Nginx에만 접속한다(WAF 경유) |
| DMZ | Nginx(WAF 뒤), portal, 공개용 DB, 포워드 프록시(Squid) | 공개 화면 서비스, 이의 제기 접수, 업무망의 외부 호출 중계 |
| 업무망 | backend-jobs, backend-api, 콘솔, core DB | 수집, 카드, 진단, 검토·승인, 공개 반영. 인터넷 직접 연결 없음 |

연결 방향 (모두 "출발 → 도착", 연결을 여는 쪽이 출발)

| # | 출발 → 도착 | 내용 | 통제 |
|---|---|---|---|
| ① | 사용자 → DMZ Nginx | 공개 화면 조회, 이의 제기 접수(POST) | WAF, TLS, GET/HEAD/POST만, IP별 요청 제한 |
| ② | Nginx → portal → 공개용 DB | 조회(읽기), 이의 제기 INSERT | portal DB 계정 `bb_portal`: 읽기 + inbox INSERT만 |
| ③ | 업무망 backend-jobs → 공개용 DB | 승인분 스냅샷 밀어넣기(push) | `bb_publisher`. 단방향. 허용 열만 |
| ④ | 업무망 backend-jobs → 공개용 DB | 이의 제기 가져오기 후 삭제 | `bb_inbox_reader`. inbox만 읽고 지움 |
| ⑤ | 업무망 backend-jobs → DMZ 포워드 프록시 | 공공 API·상용 AI 호출 | 도메인 허용목록, 모든 호출을 `core.egress_call`에 기록 |
| ⑥ | 포워드 프록시 → 인터넷 | 허용 도메인만 | `.data.go.kr .law.go.kr .kipris.or.kr .k-startup.go.kr .bizinfo.go.kr` + 상용 AI·검색 API 호스트 |
| ⑦ | 관리자 PC → console-gw | 검토 콘솔 | 127.0.0.1 또는 관리자 망에서만 |
| ✕ | DMZ → 업무망 | 없음 | 전부 차단 |

이용자가 낸 이의 제기는 DMZ inbox에 쌓이고, 업무망이 가져가 처리한 뒤 DMZ 쪽 사본을 지운다.

### 2.1 시험 배포 토폴로지

한 호스트의 docker 네트워크 여섯 개로 같은 구조를 재현한다(`deploy/test/compose.yaml`).

| 네트워크 | 붙은 것 | 비고 |
|---|---|---|
| `edge_net` | nginx | 호스트 포트 8080 공개 |
| `dmz_net` | nginx, portal, publish-db | internal(외부 차단) |
| `push_net` | backend-jobs, publish-db | internal. 연결은 backend-jobs가 연다 |
| `biz_net` | backend-jobs, backend-api, core-db | internal. DMZ 컨테이너는 붙지 않는다 |
| `egress_net` | backend-jobs, proxy | internal |
| `inet_net` | proxy | 인터넷 |
| `console_net` | console-gw, console, backend-api | internal |
| `admin_net` | console-gw | 호스트 127.0.0.1:8090으로만 노출 |

---

## 3. 구성요소별 상세

### 3.1 backend-jobs (업무망, 배치)

`pipeline/` 이미지 하나로 `bluebird` 명령을 실행한다. 리스너가 없고, 호스트에서는 systemd 타이머가 부른다.

| 명령 | 하는 일 |
|---|---|
| `ingest` | seed 파일 → core 적재. 수상자 성명·소속·팀 이름은 적재 때 지우고 익명 ID(`ID-YYYY-xxxxxxxxxx`)만 남긴다 |
| `cards` | 아이디어 카드 만들기. `card_kind` = `full`(상용 LLM이 본문을 읽음) / `local_extract`(로컬 규칙 추출) / `title_only`(제목만) |
| `sources check` | 데이터 소스가 실제로 불러와지는지 점검(`core.source_check`) |
| `signals catalog-fetch` / `catalog-import` | 공공데이터 목록개방현황 스냅샷 내려받기·가져오기 → 바뀐 것 신호 |
| `trace` / `diagnose` / `changes` / `match` / `score` | 1 흔적 → 2 막힌 이유 → 3 바뀐 것 → 시의성 점수. 사람 입력 경로 포함 |
| `review` / `top` / `funnel` | 검토·승인, 이번 주 Top 20, 깔때기 단계 보고 |
| `announce` | 공고 등록(키가 없으면 사람이 실제 공고 URL·제목·기간을 입력) |
| `publish` | 승인분 → DMZ 공개용 DB 교체(push) |
| `objections pull` / `resolve` | DMZ inbox 이의 가져오기(가져온 행은 DMZ에서 삭제) / 처리 |
| `coding sample`, `kappa` | κ용 표본 만들기, 일치도 계산 |
| `eval goldset`, `verify top20` | 골드셋 회귀, 공개 Top 20이 전문가 승인과 같은지 확인 |
| `kpi report` | G1–G13 현황표(사람 입력 대기 항목은 `human_blocked`) |

외부 HTTP는 `pipeline/bluebird/egress.py`만 한다. 다른 모듈은 직접 HTTP를 열 수 없다. egress는 허용 도메인을 확인하고, 호출마다 `core.egress_call`에 남기고, 외부로 보내도 되는 필드(`core.export_policy`)만 내보낸다.

### 3.2 backend-api (업무망, FastAPI)

`python -m bluebird.api`. 콘솔의 유일한 백엔드이고 core DB에는 최소 권한 역할 `bb_api`로 붙는다(마이그레이션 0008). 접근 토큰은 사람별로 발급하고, 서버에는 sha256 해시만 둔다(`console_users.json`). 역할:

| 역할 | 할 수 있는 일 |
|---|---|
| `reviewer` | 최종 승인·반려(`review.round = final`), 이의 처리 |
| `coder` | 2인 독립 코딩. 자기 코드만 보인다(맹검). 큐·상세는 볼 수 없다 |
| `expert` | 전문가 승인 라운드(Top 20) |
| `auditor` | 감사 라운드, 이의 열람 |

### 3.3 콘솔 (업무망, web/console)

관리자용 Next.js. 검토 큐, 아이디어 상세(승인·반려), 2인 독립 코딩, 이의 제기 처리 화면이 있다. 콘솔 앱은 internal 망에만 있어 외부로 연결하지 못하고, 앞단 `console-gw`(nginx)만 관리자 쪽에 열린다.

### 3.4 core DB (업무망)

PostgreSQL 16 + pgvector + pg_trgm. 스키마 `core`. 마이그레이션 0001–0009가 유일한 스키마 소유자다(§5).

### 3.5 공개용 DB (DMZ, publish-db)

PostgreSQL. 스키마 `publish`(승인분 사본), `meta`(템플릿·스냅샷 기록), `inbox`(이의 제기). 역할:

| 역할 | 권한 |
|---|---|
| `migrator` (`bb_migrator`) | 스키마 변경 |
| `bb_publisher` | 매 주기 `publish_next`를 만들어 이름 바꾸기로 교체 |
| `bb_inbox_reader` | inbox 읽기·삭제만 |
| `bb_portal` | publish 읽기 + inbox INSERT만 |

슈퍼유저 `bluebird`는 원격 로그인이 안 된다. 갱신은 새 스키마를 만들어 이름을 바꾸는 방식이라 포털은 이전 스냅샷 또는 새 스냅샷만 본다.

### 3.6 portal (DMZ, web/portal)

Next.js standalone. 공개용 DB를 `bb_portal`로 읽기만 하고, 쓰기는 이의 제기 inbox INSERT 하나뿐이다. 업무망 연결 정보가 없다.

### 3.7 Nginx (DMZ)

WAF 뒤에서 TLS 종료, 보안 헤더, 메서드 제한(GET/HEAD/POST 외 405), 본문 64 KB 제한, 요청 제한(API·화면·이의 제기 따로)을 건다. 이의 제기 접수는 IP당 분당 5건이라 스팸이 inbox를 채워 업무망 pull을 밀어내지 못한다. WAF 뒤라서 실제 사용자 IP는 `X-Forwarded-For`로 받는다(`docs/DEPLOYMENT.md` §5).

### 3.8 포워드 프록시 (DMZ, Squid)

업무망의 외부 호출을 대신 보낸다. 허용 도메인은 `.data.go.kr .law.go.kr .kipris.or.kr .k-startup.go.kr .bizinfo.go.kr`와 상용 AI·검색 API 호스트(`openapi.naver.com`, `api.openai.com`, `api.anthropic.com`)다. 이 목록은 `egress.py`의 `ALLOWED_HOSTS`와 같아야 하고 `verify.sh`가 비교한다. 캐시 없음, 접근 로그는 감사 보존 대상이다.

### 3.9 원칙 정리

- 상용 LLM에는 N2SF상 외부 반출이 허용된 데이터만 보낸다. 보낼 수 없는 소스는 `local_extract` 또는 `title_only` 카드로 둔다.
- 팀 이름·사람 이름은 저장하지 않는다(적재 때 익명화).
- 모든 판정에는 근거 URL이 붙는다. 근거 없는 원인은 `U`, 근거 없는 시의성 항목은 점수 없음으로 둔다.
- AI는 제안하고 사람이 승인한다(`review.round = final`). 승인 뒤 내용이 바뀌면 공개가 철회된다.

---

## 4. 처리 단계

```
ingest → cards → (1 흔적 → 2 막힌 이유 → 3 바뀐 것 → 시의성) → 깔때기 s0–s6 → review → publish → objections pull
```

| 단계 | 입력 → 출력 | 주기(운영) |
|---|---|---|
| ingest | seed 파일 → `idea`(익명 ID, 팀 이름 없음) | 매일 02:00 |
| cards | `idea` → `idea_card`(`card_kind`별) | ingest와 함께 |
| signals | 목록개방현황 내려받기 → `catalog_snapshot`, `signal_dataset`, `condition_change` | 매주 월 03:00 |
| trace / diagnose | 흔적 → `trace_check`, `trace_verdict`; 막힌 이유 → `diagnosis` + `x_evidence` | 사람·LLM 제안 후 검토 |
| changes / match | 바뀐 것 → `condition_change`; 아이디어와 연결 → `change_match` | 신호·입력 때 |
| score | 시의성 → `timeliness` (S, 판정 now/conditional/hold) | 주 1회 |
| funnel | 아래 s0–s6 계산 | SQL 한 곳 |
| top | 이번 주 재조명 → `weekly_top` 1–20 | 주 1회 |
| review | 사람 승인(`review`), 공개 허용(`publication`) | 콘솔 |
| publish | 승인분 → DMZ 공개용 DB (템플릿 v2) | 매일 06:00 |
| objections pull | DMZ inbox → `core.objection` → DMZ에서 삭제 | 10분마다 |

깔때기 단계는 `core.funnel_stage(as_of)` SQL 함수 하나가 계산한다. `bluebird funnel`도 같은 함수를 쓴다.

| 단계 | 통과 조건 |
|---|---|
| s0 | 카드가 있다 |
| s1 | 흔적 판정이 `none` 또는 `award_only`(지금 아무도 하고 있지 않다) |
| s2 | 막힌 이유가 `U`가 아니고 근거가 있다(데이터 원인 `D`면 부족한 데이터가 적혀 있다) |
| s3 | 원인과 종류가 맞는 "바뀐 것"이 연결되어 있다 |
| s4 | 시의성 판정이 `now` 또는 `conditional` |
| s5 | 사람 최종 승인과 카드·진단·시의성·바뀐 것 공개 허용이 모두 있다 |
| s6 | 공개 가능 소스이고, DMZ에 실제로 반영된 스냅샷에 들어 있다 |

공개 가능 여부는 소스별 `public_ok`로 정한다. 승인 뒤 반려·원인 변경·내용 변경이 있으면 공개 허용이 철회되어 s5에서 빠진다. 이의가 받아들여져 원본까지 공개를 멈춘 아이디어(`withheld_at`)는 깔때기·큐·Top에서 빠진다.

---

## 5. 데이터 모델

### 5.1 core (업무망) — 마이그레이션 `pipeline/bluebird/db/migrations/core/0001–0009`

| 묶음 | 표 |
|---|---|
| 원천 | `source`, `ingest_run`, `contest`, `idea`(`retired_at` 0002, `withheld_at` 0007) |
| 카드 | `idea_card`(`card_kind`, 본문 해시·`egress_call_id` 0003), `idea_embedding` |
| 근거 | `evidence`, `x_evidence` |
| 판정 | `trace_check`, `trace_verdict`(`external_search` 0009), `diagnosis`, `timeliness` |
| 바뀐 것 | `catalog_snapshot`, `signal_dataset`, `announcement`, `condition_change`(`origin` 0004), `cause_change_kind`, `change_match`(`match_eligible` 함수 0006) |
| 선정·공개 | `weekly_top`, `review`, `publication`(승인 뒤 변경 시 철회 0005), `publish_snapshot`, `export_policy` |
| 이의·코딩 | `objection`(0007), `coding_sample` |
| 감사·운영 | `egress_call`, `source_check`, `pipeline_run` |
| 깔때기 | `core.funnel_stage(as_of)` 함수(0004), `core.revival_candidate` 뷰 |

주요 규칙(DB 제약으로 강제): 카드가 `full`이면 LLM이 만들고 그 호출의 감사 행과 연결(0003), 바뀐 것 종류는 `dataset_opened`(자동 신호)·`announcement`(API 또는 사람)·`law_effective`·`policy_news`·`tech`(사람만)로 제한(0004), 종류가 원인과 안 맞으면 매칭 생성 거부(0004).

### 5.2 publish (DMZ) — 템플릿 v2 `pipeline/bluebird/publish_template/v2.sql`

| 스키마 | 표 |
|---|---|
| `publish` | `source`, `idea`, `evidence`, `diagnosis`, `change`, `timeliness`, `weekly_top`, `announcement`, `announcement_match` |
| `meta` | `publish_template`(등록된 템플릿 체크섬), `snapshot_log` |
| `inbox` | `objection`(포털 INSERT, 업무망 pull 후 삭제. `uid` 0002로 중복 판정) |

`publish`에는 템플릿에 있는 열만 나간다. 제목·본문 검색용 `pg_trgm` 인덱스가 걸려 있다. 템플릿을 바꾸려면 새 버전 파일을 만들고 migrator가 등록한다.

### 5.3 공개 범위

| 범위 | 조건 |
|---|---|
| 카드 | 소스 `public_ok` + 공개 허용 |
| 진단 | 근거 있음 + 사람 최종 승인 |
| 시의성·바뀐 것 | 사람 최종 승인 + 공개 허용. Top 20은 전문가 승인까지 |

승인되지 않은 진단은 공개 화면에 내용을 보이지 않는다.

---

## 6. 화면

### 6.1 portal (사용자 Zone → DMZ)

| 경로 | 내용 |
|---|---|
| `/` | 이번 주 재조명: `weekly_top` 1–20위 |
| `/explore` | 주제·공고 넣기: 공고 제목이나 주제를 넣으면 비슷한 아이디어(`pg_trgm`) |
| `/ideas/[id]` | 아이디어 카드: 원본 · 막힌 이유 · 바뀐 것 · 지금 하려면 · 근거 · 이의 제기 |
| `/pool` | 공개된 아이디어 목록 |
| `/api/v1/ideas`, `/api/v1/ideas/[id]` | 목록·상세 |
| `/api/v1/explore` | 주제·공고 유사 검색 |
| `/api/v1/objections` | 이의 제기 접수(POST) |

### 6.2 콘솔 (업무망, 관리자)

| 경로 | 내용 |
|---|---|
| `/` | 검토 큐 |
| `/ideas/[id]` | 아이디어 상세, 승인·반려 |
| `/coding` | 2인 독립 코딩(서로의 코드 맹검) |
| `/objections` | 이의 제기 처리(수용 시 원본 공개 중단 선택) |
| `/login` | 토큰 로그인 |

portal과 콘솔은 별도 앱·이미지로 만든다. 검토 기능 코드가 DMZ 이미지에 섞이지 않게 하기 위해서다.

---

## 7. 저장소 구조

```
bluebird/
  pipeline/                 # Python 3.12, `bluebird` CLI + backend-api
    bluebird/
      cli.py, ingest.py, cards.py, llm.py, anonymize.py
      sources.py, sources_check.py, signals/     # 소스 어댑터, 점검, 목록개방현황
      funnel.py, score.py, announce.py, wording.py
      publish.py, publish_template/{v1,v2}.sql    # 공개용 DB 반영
      objections.py, api.py                       # 이의·코딩, FastAPI
      egress.py                                   # 외부 HTTP는 여기만
      db/migrations/{core,publish}/               # 스키마 유일 소유자
    tests/
  web/
    portal/                 # DMZ 공개 포털 (Next.js standalone)
    console/                # 업무망 관리자 콘솔 (Next.js)
  deploy/
    test/                   # 단일 호스트 재현: compose.yaml, init.sh, run-cycle.sh, verify.sh, p95.sh, proxy/squid.conf
    prod/                   # nginx, postgres(pg_hba), systemd, firewall, env.example
    nginx/                  # 시험·운영 공통 nginx 스니펫
  docs/                     # ARCHITECTURE, DEPLOYMENT, SOURCES, diagrams/
  reference/                # 인수인계 원본 (커밋 제외)
```

---

## 8. 품질·보안 검증

목표는 G1–G13이다. 현황은 `bluebird kpi report`가 표로 보여주고, 사람 입력을 기다리는 항목은 `human_blocked`로 표시한다. 통제·화면 검증은 `deploy/test/verify.sh`가 한다.

| 목표 | 내용 |
|---|---|
| G1 | 모든 아이디어에 구조화 카드, `card_kind`별 건수 보고 |
| G2 | 공개용 DB의 공개 카드 수 = 공개 가능 소스의 아이디어 수 |
| G3 | κ: 표본 100건 2인 독립 코딩 ≥0.7 (`bluebird kappa`) |
| G4 | 골드셋 50건 5클래스 회귀 (`bluebird eval goldset`) |
| G5 | 이번 주 Top 20 전부 전문가 승인 (`bluebird verify top20`) |
| G6 | 관측된 새 데이터 기반 "바뀐 것" 승인·공개 건수 |
| G7 | 실제 공고 1건에 대한 매칭 표시 |
| G8 | 주제·공고 유사 검색 응답 속도(`deploy/test/p95.sh`) |
| G9 | 공개된 진단·바뀐 것·시의성마다 근거 1개 이상 |
| G10 | 반출 통제: 허용 열 밖 0, egress 밖 HTTP 0, 성명 일치 0 |
| G11 | 이의 제기 왕복: 접수 → pull → DMZ 삭제 → 처리 → 반영 |
| G12 | "바뀐 것" 무작위 20건 맹검 점검 정밀도 |
| G13 | `sources check` 결과(키 없는 소스 포함) |

`verify.sh`가 보는 것: 망 구성(DMZ·업무망 컨테이너의 외부 연결, 프록시 허용목록과 `egress.py` 일치), 공개용 DB 역할 권한, 반출 통제와 데이터 수, 원본·카드·소스 점검, 깔때기 단계, 콘솔 보안(토큰 없으면 401, 헤더, 최소 권한 DB 계정), 이의 제기 왕복, 공개 화면.

---

## 9. 일정 (본선 12월 중순)

| 날짜 | 내용 |
|---|---|
| 10/2 – 12/1 | 멘토링 기간. 의견을 시의성 가중치 등에 반영 |
| 10/12, 10/19 | 목록개방현황 스냅샷. 갱신 주기와 "바뀐 것" 목표치 판단 근거 |
| 10/26 | KIPRIS 약관·N2SF 회신 결정. 결과에 따라 KIPRIS 26,434건 공개 범위와 외부 LLM 사용 범위 확정 |
| 11/2 | E7: 추가 목표(stretch) 착수 여부 결정 |
| 11/24 – 11/30 | Top 20 전문가 검토, 바뀐 것 정밀도 점검, 반출·망 테스트 |
| 12월 중순 | 본선. 발표 수치는 DB 실측값으로 교체, 아키텍처 그림 갱신 |

---

## 10. 결정 필요 항목 (사람이 해야 해서 `human_blocked`)

1. **API 키**: K-Startup, NAVER, KIPRIS Plus, OpenAI, Anthropic, 국민권익위(권익위), 기업마당은 아직 없다. 키가 오기 전에는 `key_required`로 기록하고 사람이 입력하는 경로를 쓴다(`docs/SOURCES.md` 실측 점검).
2. **KIPRIS 약관·N2SF 등급** (10/26): 공개 범위와 외부 LLM에 보낼 수 있는 데이터를 정한다. 운영기관 보안담당과 확정.
3. **상용 LLM 무보존·학습 미사용 설정 확인**: 키를 쓰기 전에 확인한다.
4. **κ 코더 2인 지정**: 표본 100건 독립 코딩.
5. **Top 20 전문가 검토자 지정**.
6. **맹검 점검자(auditor) 지정**: 바뀐 것 정밀도 20건.
7. **LLM 예산 상한 승인**.
8. **시의성 가중치**: 초기 0.25 균등값을 멘토링 의견으로 조정.
