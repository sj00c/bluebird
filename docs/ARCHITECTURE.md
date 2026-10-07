# 파랑새(Bluebird) 배포 아키텍처 설계 v0.2 — 망분리 반영

작성 2026-10-06. 입력: 예선 제출 기획서(`reference/parangsae-src/04_deck_build/output/submitted_proposal_prelim_capital_parangsae.pdf`), 인수인계 패키지(`reference/parangsae-src/`).

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
5. **익명화와 흔적 검색이 충돌한다.** 흔적 검색에는 팀명이 필요한데, 기획서는 "적재 단계에서 삭제"로 약속했다. → 팀명은 수집존에서 질의 생성에만 쓰고 처리존·공개존에는 넘기지 않는다(§3.3). 약속을 지키면서 검색도 가능하다.

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

> 2026-10-06 변경: 인터넷망 수집 서버 + 망연계 구조와 내부 GPU(EXAONE) 계획을 접고, DMZ ②의 포워드 프록시를 통한 수집·상용 AI 호출로 바꿨다. 기준 도식은 `docs/diagrams/architecture.html`(PDF: `architecture.pdf`, 생성: `build.py`)이다. §2 이후와 `docs/DEPLOYMENT.md`, `deploy/`, `pipeline/`에는 아직 이전 구조(Z1 수집존, 망연계 번들, 내부 GPU)가 남아 있다.

### 핵심 원칙

1. **처리는 업무망에서, 노출은 DMZ ①에서, 외부 호출은 DMZ ② 프록시로만 한다.**
2. **업무망에서 밖으로 나가는 길은 DMZ ② 프록시 하나다.** 허용 도메인(공공 데이터 API, 상용 AI API)만 열고, 외부 반출이 허용되지 않은 등급의 자료는 AI 호출에 넣지 않는다.
3. **DMZ에는 공개 승인된 데이터만 반출한다.** 반출은 컬럼 허용목록 방식이고, 사람 승인이 반출 조건이다. 이것으로 기획서의 "최종 판정·공개는 담당자 확인"을 구조적으로 보장한다.
4. **망 간 전송은 파일 번들 단위로 한다.** 서명, 해시, 행 수를 담은 manifest를 붙이고, 받는 쪽은 멱등 적재한다. 망연계 솔루션 종류와 관계없이 같은 형식을 쓴다.

---

## 2. 구역 구성

```
 ┌───────── Z1 인터넷 수집존 ─────────┐      ┌──────────────── Z2 내부 처리존 (인터넷 차단) ────────────────┐
 │ collector (Python)                  │      │ importer → PostgreSQL 16 + pgvector (core 스키마)            │
 │  - data.go.kr / 디지털융합플랫폼    │ ①──▶ │ worker: normalize · extract(P1) · embed · cluster            │
 │  - KIPRIS Plus · 법제처 · 정책브리핑│ 망연계│         · diagnose(P2) · score(P3) · match                  │
 │  - K-Startup · 기업마당             │ 단방향│ llm: vLLM + EXAONE (OpenAI 호환 API, 내부 전용)              │
 │  - 금융위 · 국세청 · NAVER API HUB  │      │ embedder: BGE-M3                                            │
 │ staging (원본 보관, 번들 생성)      │      │ console (Next.js): 검토·이중 코딩·κ·공개 승인               │
 │ egress: 허용목록 도메인만           │      │ publisher: 승인분만 허용목록 컬럼으로 번들                  │
 └─────────────────────────────────────┘      └───────────────┬────────────────────────▲────────────────┘
                                                              ② 망연계 단방향         ③ 망연계 (텍스트만)
                                              ┌───────────────▼────────────────────────┴────────────────┐
                                              │ Z3 DMZ 공개존                                                  │
                                              │ portal (Next.js): 풀·진단 카드·시의성·공고 매칭·통계          │
                                              │ PostgreSQL + pgvector (publish 스키마, 읽기 전용 / inbox)     │
                                              │ embedder: BGE-M3 (공고 자유 입력 매칭용)                      │
                                              │ 알림 발송(메일 릴레이) · 구독 관리                            │
                                              │ WAF / 리버스 프록시 (TLS)                                     │
                                              └────────────────────────────────────────────────────────────────┘
```

| 흐름 | 방향 | 내용 | 통제 |
|---|---|---|---|
| ① 수집 번들 | Z1 → Z2 | 원본 레코드, 검색 결과, API 응답(NDJSON), 공고 | manifest 서명·해시, 망연계 악성코드 검사, 스키마 검증 후 적재 |
| ② 공개 스냅샷 | Z2 → Z3 | 승인된 아이디어·카드·진단·점수·근거·임베딩·공고·매칭·알림 | 컬럼 허용목록, 식별자 검사 테스트, 승인 상태 필터 |
| ③ 이용자 제출 | Z3 → Z2 | 이의 제기·정정 요청(텍스트) | 텍스트 필드만, 길이 제한, 연락처는 Z3에 남기고 티켓 ID만 전달 |

알림 구독자 정보(이메일, 관심 키워드)는 Z3 밖으로 나가지 않는다. Z2는 "신규 매칭/신규 개방 데이터" 이벤트만 스냅샷에 담고, Z3이 구독 조건과 맞춰 직접 발송한다.

### 2.1 시연용 단일 호스트 토폴로지

대회 시연(모두의 AI 실험실 클라우드)에서는 세 구역을 한 호스트의 docker 네트워크 3개로 분리한다.

- `z1_net`만 외부 egress를 허용한다. `z2_net`은 `internal: true`.
- 망연계는 공유 볼륨의 `outbox/ → inbox/` 이동기(mover)로 대체한다. 번들 형식, 검증, 적재 코드는 운영과 동일하다.
- 운영 이관 때 바뀌는 것은 mover를 실제 망연계 솔루션 연동으로 교체하는 부분과 호스트 배치뿐이다. 애플리케이션 코드는 그대로다.

---

## 3. 구역별 상세

### 3.1 Z1 수집존 — `collector`

| 소스 어댑터 | 수집 방식 | 용도 |
|---|---|---|
| `datagokr_file` | 파일 다운로드, 해시가 바뀌면 재수집 | 수상작 시드(서울시 2종, KIPRIS 아이디어 DB 15006010, 과학관, 농식품부, 공공디자인), 개방데이터 목록(15133954), 목록 메타(15121937) |
| `kstartup`, `bizinfo` | 일 1회 증분 | 공고(매칭), 후속 지원사업 선정 흔적 |
| `law` | 공포일 기간으로 전량 수집 | 제도 정합성 |
| `policy_news`, `press_release` | 기간으로 전량 수집 | 정책 수요 |
| `kipris_patent` | 아이템 키워드·팀명 질의, 연계 출원번호 772건 상태 조회 | 특허·상표 흔적 |
| `fsc_corp` → `nts_biz` | 팀명 → 법인 조회 → 사업자번호 상태 조회 | 법인·사업자 흔적 |
| `websearch` (NAVER API HUB) | 질의 2~4개/건, 상위 8건 | 뉴스·웹 흔적 |

- egress 허용목록: `apis.data.go.kr`, `www.data.go.kr`, `plus.kipris.or.kr`, `open.law.go.kr`, `www.law.go.kr`, `www.k-startup.go.kr`, `www.bizinfo.go.kr`, NAVER API HUB 도메인, 디지털융합플랫폼 도메인. 상용 LLM 도메인은 넣지 않는다.
- API 키는 Z1에만 둔다.
- 개인정보 최소수집: 과학관 수상작의 `수상자`, `지도교사`, `소속명` 같은 개인 성명·소속 컬럼은 **수집 시점에 버린다**. 번들에 들어가지 않는다.

### 3.2 망 간 번들 형식

```
bundle-<zone>-<yyyymmddHHMMSS>-<seq>/
  manifest.json   # bundle_id, source, created_at, files[{name, sha256, rows, schema_version}], prev_bundle_id
  manifest.sig    # Ed25519 서명 (구역별 키)
  <table>.ndjson.zst
```

받는 쪽 importer 처리 순서: 서명 검증 → 해시 검증 → 스키마 검증 → `bundle_log`에 기록 → 트랜잭션 적재. 같은 `bundle_id`는 무시한다(멱등). 실패한 번들은 `quarantine/`으로 옮긴다.

### 3.3 팀명 처리 — 기획서의 "적재 단계 삭제"와 흔적 검색을 동시에 만족

- 수상작 원본은 Z1이 직접 내려받으므로 팀명을 알고 있다. 흔적 질의는 **Z1이 자기 원본에서 직접 생성**한다(파일럿 `clean_team`·`masked`·`product_name` 규칙 이식). 개인 실명이나 마스킹된 팀명은 아이템명으로만 검색한다.
- Z1은 번들을 만들기 전에 팀명을 `○○`로 치환한다. 대상은 원본 레코드, 검색 결과 제목·스니펫, API 응답 전체다. 각 레코드에는 아이디어 익명 ID만 붙인다.
- 따라서 **Z2와 Z3에는 팀명이 존재하지 않는다.** 흔적 "판정"(동일 팀인지 여부)은 Z2의 LLM이 마스킹된 텍스트로 수행한다. 파일럿에서 팀명은 질의와 동일성 확인에 쓰였는데, Z1은 판정 전에 동일성 신호(`team_match: exact|partial|none`)를 계산해 함께 넘긴다.
- 익명 ID는 Z1에서 `HMAC(secret_z1, source + source_key)` 기반으로 결정적으로 생성한다. 비밀키는 Z1에만 있다.

### 3.4 Z2 내부 처리존

| 컴포넌트 | 역할 |
|---|---|
| `importer` | 번들 검증·적재, `bundle_log` |
| `worker` | 단계별 CLI(`bluebird run <stage>`) + 스케줄러. 단계는 §4 |
| `llm` | vLLM으로 EXAONE을 서빙하고 OpenAI 호환 API를 내부에만 연다. P1·P2·P3 모두 여기서 실행 |
| `embedder` | BGE-M3 dense 1024차원. 내부 HTTP |
| `console` | 검토자용 Next.js: 검증 큐, 2인 독립 코딩, κ 대시보드, 공개 승인, 이의 처리 |
| `publisher` | 승인분 스냅샷 → 번들 ② |

- 상용 LLM 토큰(기획서 19쪽 "분류·채점")은 망분리 운영에서 쓸 수 없다. 시연 환경에서도 같은 구조를 유지하기 위해 처리존의 LLM 엔드포인트는 `LLM_BASE_URL` 하나로 고정한다. 품질 비교가 필요하면 골드셋 50건으로 EXAONE과 비교 실험만 따로 한다.
- **확인 필요**: EXAONE 모델 라이선스의 공공 서비스 운영 허용 범위, GPU 사양(33B를 bf16으로 올리면 VRAM 약 70GB 필요, 양자화 시 감소).

### 3.5 Z3 DMZ 공개존

- `portal`(Next.js): 읽기 전용 화면 + `/api/v1`. DB 계정은 `publish` 스키마 SELECT, `inbox` INSERT 권한만 가진다.
- 공고 자유 입력 매칭("풀에서 찾기")은 요청 시점에 임베딩이 필요하다. 그래서 Z3에 `embedder`를 따로 둔다. 같은 모델, 같은 버전이어야 하며 스냅샷 manifest에 모델 해시를 넣어 검증한다.
- 유사 아이디어 조회 1초 목표: `publish.idea_embedding`에 HNSW 인덱스, 약 3만 건 규모에서는 충분하다.
- 이의 제기·정정 → `inbox.ticket` → 번들 ③으로 Z2 전달.
- 공개 화면 하단에 데이터 기준일, 출처, 라이선스, "AI 판정 + 담당자 확인" 문구를 표시한다.

---

## 4. 처리 단계 (Z2 worker)

| 단계 | 입력 → 출력 | 주기 |
|---|---|---|
| normalize | 수집 레코드 → `contest`, `idea` (수상등급 표기 정리, `<br />` 처리) | 번들 적재 시 |
| extract (P1) | idea → `idea_card` | 신규·변경분 |
| embed | idea_card → `idea_embedding` | 신규분 |
| cluster | 전체 임베딩 → `cluster`, `idea_tag`(3축), `similar_group` | 주 1회. 이전 군집과 매칭해 ID를 승계해서 링크가 깨지지 않게 한다 |
| trace-judge | 마스킹 흔적 결과 + `team_match` → `trace_check`(4종), `trace_verdict`(5클래스) | 흔적 번들 적재 시 |
| diagnose (P2) | 카드 + 근거 → `diagnosis`(T·D·R·M·C·O·U) | `trace_verdict ≠ realized` |
| score (P3) | 카드 + 개방목록 diff·법령·정책뉴스(임베딩 매칭으로 관련 항목 추림) → `timeliness` | 주 1회 + 데이터 개방 이벤트 |
| match | 신규 공고 → 코사인 Top-50 → S 재확인 → Top-N | 공고 번들 적재 시 |
| publish | 승인분 → 번들 ② | 일 1회 |

시의성 신호 수집이 Z2로부터의 질의 없이 가능한 이유: 법령·정책뉴스·개방목록은 기간 단위로 전량 수집하고, 아이디어와 관련된 항목은 Z2에서 임베딩·키워드로 고른다. 그래서 내부망에서 인터넷 방향의 흐름이 생기지 않는다.

LLM 출력 저장 규칙: `model`, `prompt_version`, `evidence_ids`를 항상 저장한다. 근거가 비어 있으면 원인은 `U`, 시의성 항목은 `null`(판단 불가)로 강제한다. DB CHECK와 코드 양쪽에서 막는다.

---

## 5. 데이터 모델

**core (Z2)** — 단일 소유자 Alembic

- `bundle_log(bundle_id, zone, source, received_at, status, rows)`
- `source(id, name, license, url, layer, public_ok bool)` — KIPRIS 벌크는 `public_ok=false`
- `contest(id, source_id, name, host_org, year)`
- `idea(id, contest_id, year, award, title, body, used_data[], source_url)` — 팀명 없음, 원문 무변형
- `idea_card(idea_id, title, problem, solution, target_user, required_data[], required_tech[], domain, year, source_url, model, prompt_version)` — P1, 기획서 필드 그대로
- `idea_embedding(idea_id, model, vec vector(1024))`
- `cluster`, `idea_cluster`, `idea_tag(axis∈{topic,tech,problem})`, `similar_group`, `similar_member`
- `evidence(id, idea_id, kind, url, title, excerpt_masked, observed_at, collected_at, bundle_id)`
- `trace_check(idea_id, item∈{news_web,corp_biz,ip,program}, result∈{found,none,unknown}, count, evidence_ids[])`
- `trace_verdict(idea_id, status∈{realized,pivot,similar_unlinked,award_only,none}, confidence, reason, evidence_ids[], model, prompt_version)`
- `diagnosis(idea_id, primary∈TDRMCOU, secondary, confidence, rationale, evidence_ids[], model, prompt_version)`
- `timeliness(idea_id, as_of, tech, data, regulation, policy (각 0~5 또는 null), weights jsonb, s, verdict∈{now,conditional,hold}, resolve_condition, changes[≤3], evidence jsonb)`
- `announcement(id, source, title, body, org, apply_from, apply_to, url, vec)`, `match(announcement_id, idea_id, similarity, s, verdict, rank)`
- `review(id, target_type, target_id, reviewer, round∈{coder_a,coder_b,final}, decision, code, note, created_at)` — κ 계산 원천
- `publication(idea_id, scope∈{pool,diagnosis,timeliness}, approved_by, approved_at, revoked_at)` — 반출 게이트
- `ticket(id, idea_id, kind∈{objection,correction}, body, status, resolution)` — 번들 ③에서 적재
- `pipeline_run(id, stage, started_at, finished_at, status, stats, error)`

**publish (Z3)** — core의 부분집합. 허용목록 컬럼만 둔다. `publisher`가 허용목록에 없는 컬럼이 들어 있으면 실패하도록 테스트로 강제한다.

**inbox (Z3)** — `ticket_submission`, `subscription`(Z3 전용, 반출하지 않음).

공개 범위:

| scope | 공개 조건 |
|---|---|
| pool (카드·태그·군집·유사 묶음) | 출처가 `public_ok`이고 P1 스키마 검증을 통과 |
| diagnosis (흔적·원인) | `review` final 승인 |
| timeliness (S·판정·달라진 점) | `review` final 승인. 재발굴 후보 Top 20은 전문가 검토 기록까지 필요 |

승인되지 않은 진단은 공개 화면에 "검증 대기"로만 표시하고 내용은 보여주지 않는다.

---

## 6. 화면

**portal (Z3)** — 목업 기준

| 경로 | 내용 |
|---|---|
| `/pool` | 목록·필터(군집, 연도, 도메인, 원인, S) |
| `/ideas/[id]` | 진단 카드(mock_a): 태그, 흔적 확인표, 원인, 시의성 4막대, 달라진 점, 관련 공고, 근거 링크(새 탭), 이의 제기 |
| `/timeliness` | 재조명 후보(S≥4.0, 승인분) |
| `/matching` | 공고 선택 또는 자유 입력 → Top-N (mock_b) |
| `/stats` | 풀 현황, 원인 분포(검증 완료 건 기준), 기관별 분포(주최기관 모드) |
| `/api/v1/*` | `ideas`, `ideas/{id}`, `ideas/{id}/similar`, `announcements`, `match`, `stats`, `tickets` |

**console (Z2)** — 검증 큐, 2인 독립 코딩(서로의 판정을 볼 수 없음), κ 현황(목표 0.7), 공개 승인, 이의 처리, 파이프라인 실행 현황.

portal과 console은 별도 앱으로 빌드한다. 하나의 앱에 플래그를 두면 DMZ 이미지에 검토 기능 코드가 섞여 반출되기 때문이다. 화면 컴포넌트만 공유 패키지로 둔다.

---

## 7. 저장소 구조

```
bluebird/
  pipeline/                  # Python 3.12, uv — 구역 공용 CLI `bluebird`
    bluebird/
      bundle.py              # manifest·서명·검증·이동 (Z1/Z2/Z3 공용)
      collector/             # Z1: 소스 어댑터, 팀명 마스킹·익명 ID
      db/migrations/{core,publish}/  # SQL 마이그레이션(스키마 유일 소유자)
      stages.py              # collect, import-core, publish, import-publish (+ 예정 단계)
      cli.py
    tests/
    Dockerfile
  web/portal/                # Z3 공개 포털 (Next.js standalone)
  deploy/
    nginx/                   # 시험·운영 공통 nginx 스니펫
    test/                    # 단일 호스트 3구역 재현(compose, init/run-cycle/verify)
    prod/                    # nginx TLS, PostgreSQL, systemd, 방화벽표, env 예시
  docs/
  reference/                 # 인수인계 원본 (커밋 제외)
```

LLM 클라이언트·프롬프트(P1~P3), 검토 콘솔(`web/console`)은 해당 단계를 구현할 때 같은 구조에 추가한다. 파이프라인 이미지 1개를 구역별 명령으로 나눠 쓰고, 포털은 별도 이미지다. 내부망 반입은 이미지 tar + 서명 방식으로 한다(빌드는 인터넷망 CI에서). 구현·배포 상세는 `docs/DEPLOYMENT.md`.

---

## 8. 품질·보안 검증 항목

- 골드셋 50건 회귀: 프롬프트나 모델을 바꿀 때 5클래스 일치율과 혼동행렬을 리포트한다.
- κ: 표본 100건 2인 독립 코딩. `review` 테이블로 계산한다.
- 반출 테스트: publish 번들에 허용목록 밖 컬럼이 없는지, 팀명 사전과 일치하는 문자열이 없는지 확인한다.
- 마스킹 테스트: Z1 번들 전체에서 원본 팀명이 남아 있지 않은지 확인한다.
- egress 테스트: Z2 컨테이너에서 외부 연결이 실패하는지 확인한다(시연 토폴로지).
- 근거 링크 100%: 공개된 진단·점수의 `evidence_ids`가 비어 있지 않은지 DB CHECK로 강제한다.

---

## 9. 일정 (본선 12월 중순)

| 기간 | 결과물 |
|---|---|
| 10/6~10/12 | API 키 확보(NAVER API HUB, data.go.kr, KIPRIS Plus, 법제처). 번들 형식, core 스키마, 시연 토폴로지, collector(수상작·KIPRIS 파일) → importer → normalize |
| 10/13~10/26 | P1 카드, 임베딩, 군집. portal `/pool`·`/ideas/[id]` 실데이터 연결 (기획서 1단계 만회) |
| 10/27~11/9 | 흔적 수집(2층 전수), trace-judge, P2, 골드셋 회귀, console 검증 큐 |
| 11/10~11/23 | P3 시의성, 공고 매칭, publish 번들, `/matching`·`/stats` |
| 11/24~12/1 | κ 측정, Top 20 전문가 검토, 이의 제기 흐름, 알림 |
| 12월 | 시연 데이터 고정, 발표 수치를 DB 실측값으로 교체, 아키텍처 그림 갱신(RAGFlow·Superset·Supabase 제거, 3구역 표기) |

---

## 10. 결정 필요 항목

1. 운영 주체와 망분리 체계: 운영기관 보안담당과 N2SF 등급(O/S)과 망연계 솔루션 종류를 확정한다. 본선 시연은 §2.1 토폴로지로 진행한다.
2. LLM 호스팅: 처리존 GPU 사양, EXAONE 라이선스의 공공 서비스 운영 허용 여부.
3. 웹검색 공급자: NAVER API HUB 가입 가능 여부.
4. KIPRIS 공개 범위: data.go.kr 15006010 파일의 실제 컬럼과 이용조건을 확인한다(벌크와의 차이).
5. 시의성 가중치: 초기 0.25 균등값을 멘토링 의견으로 조정한다(기획서 14쪽).
