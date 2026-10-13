# 파랑새 (Bluebird)

공모전 수상 아이디어 수집 → 정리·공개 서비스.

- 왜 사업이 안 됐는지
- 그 뒤 무엇이 바뀌었는지
- 지금 다시 해볼 만한지

- 원본 아이디어 풀: 출처 공개 허용 범위 안에서만 표시
- **진단·바뀐 것·시의성 분석: 근거 + 사람 최종 승인 후 공개**
- 미검색·근거 부족·키 미설정 ≠ 검색 결과 없음·0점
- 현재 = **로컬 데모**. Docker로 내 PC에서 전부 실행

## 문서

| 문서 | 내용 |
|---|---|
| `docs/DATA.md` | 소스별 사이트/API·연도·건수·주제(`./demo.sh export`가 생성) |
| `docs/ARCHITECTURE.md` | 설계. 흐름·DB 스키마·코드 경계·결정 필요 항목 |
| `docs/diagrams/` | 구성도 |

## 구성

| 서비스 | 주소 | 하는 일 |
|---|---|---|
| 포털 | http://localhost:3000 | 시민용 화면 (이번 주 재조명, 주제·공고로 찾기, 아이디어 카드, 이의 제기) |
| 콘솔 | http://localhost:3001 | 관리자 화면 (검토, 승인, 2인 코딩, 이의 처리) |
| 백엔드 API | http://localhost:8000 | 콘솔용 API |
| DB | 127.0.0.1:54329 | PostgreSQL 1개. 원본 DB(`bluebird_core`) + 공개 DB(`bluebird_publish`) |
| 처리 작업 | (명령 실행) | 적재, 카드 생성, 바뀐 것 수집, 소스 점검, 이의 가져오기, 공개, 성과 지표 |

- 포털 = 공개 DB만 접근
- 원본 DB → 공개 DB 이동 = 처리 작업만
- 설계: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) / 데이터: [docs/DATA.md](docs/DATA.md)

### 코드 경계와 도구 독립성

- API: 조립 → HTTP 인증·스키마·라우트 → 조회/도메인 워크플로 분리
- 포털: 공개 DB 접근 / 표현 분리. 콘솔: 서버 전송 / 기능별 화면 분리
- 의존 방향 상세: [아키텍처의 코드 경계](docs/ARCHITECTURE.md#11-코드-경계와-의존-규칙)
- Claude·Codex·GJC·개인 PC 스크립트: 실행에 불필요. `.gjc/` = 무시되는 로컬 이력, 애플리케이션 미참조
- 필수 프레임워크 유지. 새 UI·차트·폰트 패키지 추가 없음
- 빌드: `npm ci`, `uv sync --frozen` (잠금 파일 사용)

### 화면과 글꼴

- 포털: 좁은 메뉴 레일, 검색·필터, 선택 가능한 공개 기록 8건, 비대칭 상세 패널, 주간 선정·검토 도구
- 콘솔: 우선 대기열, 단계별 상태, 연결 점검, 공개 반영, 역할별 작성·검토
- 화면 문구: 라벨·불릿·상태 표시. 원문·긴 검토 근거 = 내용 변경 없이 접기
- 공통 디자인: 흰 작업면, 검정 텍스트·선택·버튼, 회색 구분선. 좁은 화면 = 가로 메뉴·세로 작업 배치
- 기록 선택: 클릭·위아래 방향키·Home/End. 선택 기록의 실제 메타데이터·원본 링크 표시
- 글꼴: Pretendard Variable 1.3.9 자체 호스팅(라이선스 포함). 필요 글자 묶음만 WOFF2, 버전별 캐시, `font-display: swap`. 외부 글꼴 CDN 불필요
- WebGPU: 포털 전체 경로 공유 무채색 배경 캔버스 1개. 작은 히어로 일러스트 없음
- 렌더링: `shaders` 코어 API 해상도 조절, 24fps 상한. DPR 고려 버퍼 ≤ 60만 픽셀
- 대체 화면: 1024px 미만·모션 감소·GPU 미지원 → 동일 계열 CSS 배경. 움직임 끄기·숨긴 탭 → 렌더러 해제
- 데이터·입력·탐색: 캔버스 밖 HTML. 콘솔 = 같은 디자인의 정적 표면


## 처음 띄우기 (팀원용)

필요 조건: **Docker Desktop**.

1. 원본 데이터 → `data/seed/`
   - 원본 데이터 = git 제외(수상자 이름 포함, 별도 전달). 다운로드 위치 = `deploy/local/sources.toml`의 `url`
   - 나머지 소스: `./demo.sh collect`가 직접 수신. 파일 배치 불필요

   ```
   data/seed/awards_master_2013_2024.csv                 # 범정부 공공데이터 창업경진 예선(15146089)
   data/seed/gov_opendata_startup_contest_final_awards_2019_2025.xlsx   # 본선(15146087)
   data/seed/national_science_museum_awards_20240909.csv # 국립중앙과학관(15135618)
   data/seed/mafra_agrifood_bigdata_contest_info.csv     # 농식품부(15131197)
   data/seed/public_design_idea_15138745.csv             # 공공디자인 국민아이디어공모
   data/seed/catalog_snapshot0_2026-10-06.csv            # 목록개방현황 스냅샷 #0(선택)
   ```

   인수인계 zip 그대로 사용 = 압축 푼 디렉터리를 인수로: `./demo.sh init reference/parangsae-src`

2. 순서대로 실행

   ```
   ./demo.sh init      # .env, 익명화 키, 콘솔 로그인 토큰, 원본 파일 준비 (처음 한 번)
   ./demo.sh cycle     # 빌드 → 원본 적재·소스 점검·카탈로그 → 승인분 공개 → 화면
   ./demo.sh tokens    # 콘솔 로그인 토큰 보기 (reviewer1 등)
   ```

   - 처리 시간 = 원본 규모·외부 응답에 따라 가변. 수집 건수 ≠ 공개 건수
   - 완료 시 포털·콘솔 주소 출력
   - `./demo.sh status`: 컨테이너, API·포털 DB 연결, 콘솔 로그인 화면 상태 확인


## 공식 원본 수집

```sh
./demo.sh collect                                  # 검증된 공식 출처 → 원본 DB
./demo.sh collect --only happy_rural_community_awards # 출처 하나만 갱신
./demo.sh collect --download-only                  # 검증·보관만, 아이디어 적재 제외
```

- 출처 레지스트리: `deploy/local/contest-sources.toml`, `science-contest-sources.toml`, `design-contest-sources.toml`, `api-sources.toml`. 소스 목록 = `docs/DATA.md`
- OpenAPI 6종 = 키 필요(`SEOUL_OPENAPI_KEY`·`DATA_GO_KR_KEY`·`GG_OPENAPI_KEY`·`KIPRIS_PLUS_KEY`). 국민신문고 = 건별 조회, 일 한도 10,000 → 1회 실행 = `BB_ACRC_CALL_BUDGET`(기본 9,000)회까지 증분
- `./demo.sh schedule` = 국민신문고 매일 00:30 자동 수집(launchd, 이 Mac 로그인 중). `schedule off` = 해제
- 원본 보관: 읽기 전용 `/seed` 유지. 추가 수집 파일 = 비공개 `/signals/contests`
- 검증: 명시적 컬럼 매핑, 원천 ID 또는 수집 콘텐츠 기반 ID, 중복 제거, 제공 성명 마스킹. 제목 없는 행·공고·공식 합성 데이터 = 적재 제외
- 실패: 잘못된 응답·페이지 누락·적재 실패 → 기존 정상 파일 유지. 동일 파일 재수집 = 중복 적재 없음
- 권한: 신규 수집 = `public_ok=false`, `export_grade=pending`. 공개 웹 열람 가능 ≠ 재배포 허가
- 해석: 수집 과정에서 카드·사업화 판정·원인·점수·매칭·승인 생성 없음. `cycle`도 분석 명령 자동 실행 없음
- 실행: 국민신문고 외 갱신 = `./demo.sh collect` 명시 실행

## 검토부터 공개까지

1. 콘솔 **수집 원본**: 카드·분석 생성 전 자료 검색, 상세의 **공식 원문** 링크로 출처 확인. 기본 대기열 `raw`, 기존 검토 단계 `s0–s6`
2. **운영 개요**: 전체 수집량 vs 카드·분석 단계 수 구분, 출처 권한·API 키 대기·마지막 공개 시각 확인
3. `reviewer`: 아이디어 상세에서 흔적 확인 → 근거 붙인 원인 진단 → 기존 변화 연결 → 4축 시의성 점수 저장 → 최종 승인. 전문가 승인 = 별도 `expert` 라운드
4. `./demo.sh publish`: 이의 접수함 가져오기 → 이번 주 재조명 선정 → 공개 스냅샷 교체. 시민 화면 반영 = 이 배치 완료 후(콘솔 저장 직후 아님)
5. 시민 이의: 같은 가져오기 배치 이후 콘솔에서 처리. 수용 → 분석 승인 철회. **원본까지 공개 중단** 선택 → 원본도 다음 공개에서 제외. 승인된 근거·진단·점수 변경 → 재승인 필요

- `coder` = 독립 코딩 화면만. `auditor` = 이의 읽기·감사 라운드만
- 코더: 상대 코드·검토 상세 열람 불가

## API 키 넣기

- `.env`에 키 입력 → `./demo.sh check`로 접근 가능 여부 확인
- 키 없는 소스 = `key_required` 표시. 나머지 로컬 기능 정상
- 키 입력만으로 자동 분석 실행·결과 공개 없음

| 키 | 채워지는 것 | 발급 |
|---|---|---|
| `OPENAI_API_KEY` 또는 `ANTHROPIC_API_KEY` | 카드 요약(P1), 근거 제한 원인 제안(P2), 시의성 제안(P3) | 각 사이트 |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 사업화 흔적: 후속 보도 | NAVER API HUB(네이버클라우드 NCP 콘솔, 결제 수단 등록 필요) |
| `KIPRIS_PLUS_KEY` | 공모전 아이디어DB 수집(월 1,000회 중 386회), 사업화 흔적 후보: 특허·실용신안 검색 | plus.kipris.or.kr |
| `DATA_GO_KR_KEY` | K-Startup 공고 수집, 국민신문고 공개제안 수집(15059423), 권익위 공모제안 연결 점검 | data.go.kr (키 1개 공용, 서비스별 활용신청) |
| `SEOUL_OPENAPI_KEY` | 서울 시민참여예산·법령제도개선 제안·자유제안 수집 | data.seoul.go.kr 일반 인증키 |
| `GG_OPENAPI_KEY` | 경기 주민참여예산 제안사업 수집 | data.gg.go.kr OpenAPI |
| `BIZINFO_KEY` | 기업마당 API 연결 점검; 전체 공고 수집 미구현 | bizinfo.go.kr (선택) |
| `LAW_OC` | 법령 (비우면 시험 계정) | open.law.go.kr (선택) |

자동 제안: 비용·검토 범위 제한, 명시적 실행. 기본 1건, 최대 20건, `--idea <ID>`로 1건 지정 가능.

```sh
./demo.sh job trace auto --limit 1       # NAVER 뉴스·KIPRIS 특허/실용신안 검색
./demo.sh job diagnose auto --limit 1    # 원문 발췌 근거를 검증하는 P2 제안
./demo.sh job score auto --limit 1       # 기존 변화 근거에 제한한 P3 제안
```

- 자동 검색 = 채널별 첫 페이지 최대 10건 제한 검색
- 발견 = 사업화 확정 아님. 담당자가 해석할 후보
- 법인·상표·지원사업 **선정 이력** 자동 확인 없음
- 키 누락·실패 = `미실시`
- AI 제안: 반출 허용 O급 자료만 사용. 기존 사람 진단·점수 덮어쓰기 없음. 자동 승인 없음

## 데이터 공유

- `./demo.sh export` → `.runtime/export/bluebird_ideas_YYYYMMDD.xlsx` 1파일(전체). 시트: caution / ideas / sources / contests / exclusion_reason
  - `share` 열 = 가능 / 보류. 소스별 레지스트리 `share = true|false`(원 기관 이용조건 확인한 사람이 적음). 보류 행 = 외부 반출 금지
  - 수상자·제안자 이름 = 적재 시 제거. 본문 잔존 이름 = 원 기관 공개본 그대로
- `ideas.exclude_reasons` = "뺀다면 이 이유" 후보(초·중·고 학생 대회, 참여예산 제안 등). 필터링 없음, 받는 쪽이 선택. 뜻 = `exclusion_reason` 시트
- `ideas.canonical_id` = 같은 아이디어의 다른 기록이면 묶음 대표 id(재제출·중복 등록, 출품작·수상작·KIPRIS 목록). 이 행에는 `duplicate_record` 이유가 붙음. 대표·단독 = 빈 값
- 소스별 사이트·연도·건수·주제: `docs/DATA.md` (export마다 재생성)

## 자주 쓰는 명령

```
./demo.sh up            # 전부 켜기
./demo.sh down          # 끄기 (데이터 유지)
./demo.sh status        # 서비스·DB 연결 상태 확인 (데이터 변경 없음)
./demo.sh check         # 외부 API·원본 파일 연결 점검표
./demo.sh collect       # 공식 공모전·제안 원본 수집 (분석·승인 생성 없음)
./demo.sh policy        # 소스 설정 파일(TOML)의 기록 종류·제외 후보 이유만 DB 반영 (파일 재수집 없음)
./demo.sh export        # 공유용 xlsx(.runtime/export/, share 열로 가능/보류) + docs/DATA.md
./demo.sh schedule      # 국민신문고 공개제안 매일 00:30 수집 등록. schedule off = 해제
./demo.sh publish       # 이의 가져오기 → 재조명 선정 → 공개 반영
./demo.sh job <명령>     # 처리 작업 1회 실행. 예: job funnel, job kpi report
./demo.sh verify        # 회귀 시연 점검. 이의·공개 데이터 변경 → 일회용 환경 전용
./demo.sh logs portal   # 로그 보기
```

## 개발할 때 (DB만 Docker)

- 코드 수정 즉시 반영 = DB만 Docker, 나머지 직접 실행
- 필요: Python 3.12(uv), Node 20 이상

```
./demo.sh up db
eval "$(./demo.sh env)"          # DB 주소, 키, 경로를 현재 셸에 설정

cd pipeline && uv sync && uv run bluebird funnel     # 처리 작업
uv run python -m bluebird.api                        # 백엔드 API :8000
cd web/portal  && npm install && npm run dev         # 포털 :3000
cd web/console && npm install && npm run dev -- -p 3001   # 콘솔 :3001
```

- Docker api·portal·console과 포트 충돌 → 직접 실행 전 `docker compose stop api portal console`

테스트:

```
docker run -d --name bb-testdb -e POSTGRES_PASSWORD=t -p 55432:5432 pgvector/pgvector:pg16
cd pipeline && BB_TEST_DSN=postgresql://postgres:t@localhost:55432/postgres uv run pytest -q
uv run ruff check bluebird tests
```

- 테스트 DB = 일회용 필수. 테스트가 DB 역할·표본 생성, 권한 변경
- 실제 시연 데이터 DB에 `BB_TEST_DSN` 연결 금지. 실행 확인만 = `./demo.sh status`

기존 데이터 유지 + 코드만 갱신:

```sh
docker compose build api portal console
./demo.sh job migrate --target core
docker compose up -d --no-build --wait api portal console
./demo.sh status
```

- 로컬 시연용. 인터넷 공개 시 인증·요청 제한·비밀키 관리·운영망 분리 = 별도 운영 설계 필요

## 구성도 보기

- 표준 Python만으로 생성·미리보기. 개인 경로·전용 터미널 뷰어 불필요

```sh
python3 docs/diagrams/build.py
./docs/diagrams/preview.sh       # http://127.0.0.1:8765/architecture.html
```

PDF 필요 시만 로컬 Chromium 지정:

```sh
python3 docs/diagrams/build.py --pdf --browser /path/to/chromium
```
