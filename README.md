# 파랑새 (Bluebird)

공모전 수상 아이디어를 모아서 다음 내용을 정리해 보여 주는 서비스예요.

- 그 아이디어가 왜 사업이 안 됐는지
- 그 뒤로 무엇이 바뀌었는지
- 지금 다시 해볼 만한지

원본 아이디어 풀은 출처의 공개 허용 범위 안에서 보여 줘요. **진단·바뀐 것·시의성 분석은 근거와 사람의 최종 승인이 있어야 공개**돼요. 미검색·근거 부족·키 미설정을 검색 결과 없음이나 0점으로 바꾸지 않아요.

지금은 **로컬 데모**예요. 내 PC에서 Docker로 전부 띄워요.

## 구성

| 서비스 | 주소 | 하는 일 |
|---|---|---|
| 포털 | http://localhost:3000 | 시민용 화면 (이번 주 재조명, 주제·공고로 찾기, 아이디어 카드, 이의 제기) |
| 콘솔 | http://localhost:3001 | 관리자 화면 (검토, 승인, 2인 코딩, 이의 처리) |
| 백엔드 API | http://localhost:8000 | 콘솔이 쓰는 API |
| DB | 127.0.0.1:54329 | PostgreSQL 하나에 원본 DB(`bluebird_core`)와 공개 DB(`bluebird_publish`)가 같이 있어요 |
| 처리 작업 | (명령으로 실행) | 적재, 카드 만들기, 바뀐 것 수집, 소스 점검, 이의 가져오기, 공개, 성과 지표 |

- 포털은 공개 DB만 볼 수 있어요.
- 원본 DB에서 공개 DB로 옮기는 건 처리 작업만 해요.
- 자세한 설계는 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), 데이터 소스는 [docs/SOURCES.md](docs/SOURCES.md)에 있어요.

### 코드 경계와 도구 독립성

API는 조립 → HTTP 인증·스키마·라우트 → 조회/도메인 워크플로로 분리되어 있어요. 포털은 공개 DB 접근과 표현, 콘솔은 서버 전송과 기능별 화면을 나눠요. 상세한 의존 방향은 [아키텍처의 코드 경계](docs/ARCHITECTURE.md#11-코드-경계와-의존-규칙)를 보세요.

Claude·Codex·GJC나 개인 PC의 스크립트는 실행에 필요하지 않아요. 기존 `.gjc/`는 무시되는 로컬 이력일 뿐 애플리케이션이 읽지 않아요. 필수 프레임워크는 유지하고, 새 UI·차트·폰트 패키지를 추가하지 않았어요. 빌드는 `npm ci`와 `uv sync --frozen`으로 잠금 파일을 사용해요.

### 화면과 글꼴

- 포털: 좁은 메뉴 레일, 검색·필터, 선택 가능한 공개 기록 8건, 비대칭 상세 패널, 주간 선정·검토 도구.
- 콘솔: 우선 대기열, 단계별 상태, 연결 점검, 공개 반영, 역할별 작성·검토.
- 화면 문구: 라벨·불릿·상태 표시. 원문·긴 검토 근거는 내용 변경 없이 접기.
- 공통 디자인: 흰 작업면, 검정 텍스트·선택·버튼, 회색 구분선. 좁은 화면은 가로 메뉴·세로 작업 배치.
- 기록 선택: 클릭·위아래 방향키·Home/End 지원. 선택한 기록의 실제 메타데이터와 원본 링크 표시.

Pretendard Variable 1.3.9를 라이선스와 함께 자체 호스팅해요. 필요한 글자 묶음만 WOFF2로 받고, 버전별 캐시와 `font-display: swap`을 사용해요. 외부 글꼴 CDN은 필요하지 않아요.

- WebGPU: 포털 전체 경로에서 공유하는 무채색 배경 캔버스 1개. 작은 히어로 일러스트는 사용하지 않아요.
- 렌더링: `shaders` 코어 API의 해상도 조절과 24fps 상한. DPR을 고려해 버퍼를 60만 픽셀 이하로 제한해요.
- 대체 화면: 1024px 미만·모션 감소·GPU 미지원은 동일 계열의 CSS 배경. 움직임 끄기·숨긴 탭은 렌더러 해제.
- 데이터·입력·탐색: 캔버스 밖의 HTML. 콘솔은 같은 디자인의 정적 표면을 사용해요.


## 처음 띄우기 (팀원용)

필요한 건 **Docker Desktop** 하나예요.

1. 원본 데이터를 받아서 `data/seed/`에 둬요.
   - 원본 데이터는 git에 없어요. 수상자 이름이 들어 있어서 따로 전달해요.
   - 파일 이름과 내려받는 곳은 `docs/DATA_PROVENANCE.md`(출처 명세)에 있어요. 없는 파일은 건너뛰고 나머지만 적재돼요.
   - 60개 공모전·제안 소스는 `./demo.sh collect`가 공공데이터포털에서 직접 받아요. 파일을 둘 필요가 없어요.

   ```
   data/seed/awards_master_2013_2024.csv                 # 범정부 공공데이터 창업경진 예선(15146089)
   data/seed/gov_opendata_startup_contest_final_awards_2019_2025.xlsx   # 본선(15146087)
   data/seed/national_science_museum_awards_20240909.csv # 국립중앙과학관(15135618)
   data/seed/mafra_agrifood_bigdata_contest_info.csv     # 농식품부(15131197)
   data/seed/public_design_idea_15138745.csv             # 공공디자인 국민아이디어공모
   data/seed/kipris_idea_master.csv                      # KIPRIS Plus 벌크(공개 보류 소스, 선택)
   data/seed/catalog_snapshot0_2026-10-06.csv            # 목록개방현황 스냅샷 #0(선택)
   ```

   인수인계 zip을 그대로 쓰려면 압축을 푼 디렉터리를 인수로 줘요: `./demo.sh init reference/parangsae-src`

2. 아래 명령을 차례로 실행해요.

   ```
   ./demo.sh init      # .env, 익명화 키, 콘솔 로그인 토큰, 원본 파일 준비 (처음 한 번)
   ./demo.sh cycle     # 빌드 → 원본 적재·소스 점검·카탈로그 → 승인분 공개 → 화면
   ./demo.sh tokens    # 콘솔 로그인 토큰 보기 (reviewer1 등)
   ```

   - 처리 시간은 원본 규모와 외부 응답에 따라 달라져요. 수집 건수와 공개 건수는 별개예요.
   - 끝나면 포털과 콘솔 주소가 출력돼요.

   - `./demo.sh status`로 컨테이너와 API·포털 DB 연결, 콘솔 로그인 화면의 상태를 확인해요.


## 공식 원본 수집

```sh
./demo.sh collect                                  # 검증된 공식 출처 → 원본 DB
./demo.sh collect --only happy_rural_community_awards # 출처 하나만 갱신
./demo.sh collect --download-only                  # 검증·보관만, 아이디어 적재 제외
```

- 출처 레지스트리: `deploy/local/contest-sources.toml`, `science-contest-sources.toml`, `design-contest-sources.toml`.
- 범위: 공식 CSV 55종, 과학관 아카이브 2종, 한국디자인진흥원 갤러리 3종. 시민제안·개선과제는 공모전 수상작과 별도 구분.
- 원본 보관: 읽기 전용 `/seed` 유지. 추가 수집 파일은 비공개 `/signals/contests`에 저장.
- 검증: 명시적 컬럼 매핑, 원천 ID 또는 수집 콘텐츠 기반 ID, 중복 제거, 제공된 성명 마스킹. 제목 없는 행·공고·공식 합성 데이터는 적재 제외.
- 실패: 잘못된 응답·페이지 누락·적재 실패 시 기존 정상 파일 유지. 같은 파일 재수집은 중복 적재하지 않음.
- 권한: 신규 수집은 `public_ok=false`, `export_grade=pending`. 공개 웹 열람 가능성과 재배포 허가는 별개.
- 해석: 수집 과정에서 카드·사업화 판정·원인·점수·매칭·승인을 만들지 않음. `cycle`도 분석 명령을 자동 실행하지 않음.
- 실행: 저장소에 예약 수집 설정 없음. 갱신은 `./demo.sh collect`로 명시 실행. 실제 적재 건수·중복·제한은 [소스 조사](docs/SOURCES.md) 참고.

## 검토부터 공개까지

1. 콘솔의 **수집 원본**에서 카드·분석 생성 전 자료도 검색하고 상세의 **공식 원문** 링크로 출처를 확인해요. 기본 대기열은 `raw`, 기존 검토 단계는 `s0–s6`예요.
2. **운영 개요**에서 전체 수집량과 카드·분석 단계 수를 구분하고, 출처 권한·API 키 대기·마지막 공개 시각을 확인해요.
3. `reviewer`로 아이디어 상세에서 흔적 확인, 근거를 붙인 원인 진단, 기존 변화와의 연결, 4축 시의성 점수를 저장하고 최종 승인해요. 전문가 승인은 별도 `expert` 라운드예요.
4. `./demo.sh publish`가 이의 접수함 가져오기 → 이번 주 재조명 선정 → 공개 스냅샷 교체를 실행해요. 콘솔 저장 직후가 아니라 이 배치가 끝난 뒤 시민 화면에 반영돼요.
5. 시민의 이의는 같은 가져오기 배치 이후 콘솔에서 처리해요. 수용하면 분석 승인이 철회되고, **원본까지 공개 중단**을 선택하면 원본도 다음 공개에서 빠져요. 승인한 근거·진단·점수를 바꿔도 다시 승인해야 해요.

`coder`는 독립 코딩 화면만, `auditor`는 이의 읽기와 감사 라운드만 사용할 수 있어요. 코더는 상대방의 코드나 검토 상세를 볼 수 없어요.

## API 키 넣기

`.env`에 키를 넣고 `./demo.sh check`로 접근 가능 여부를 확인해요. 키가 없는 소스는 `key_required`로 표시되고 나머지 로컬 기능은 정상 동작해요. 키를 넣는 것만으로 아래 자동 분석이 실행되거나 결과가 공개되지는 않아요.

| 키 | 채워지는 것 | 발급 |
|---|---|---|
| `OPENAI_API_KEY` 또는 `ANTHROPIC_API_KEY` | 카드 요약(P1), 근거 제한 원인 제안(P2), 시의성 제안(P3) | 각 사이트 |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 사업화 흔적: 후속 보도 | developers.naver.com |
| `KIPRIS_PLUS_KEY` | 사업화 흔적 후보: 특허·실용신안 검색 (상표 검색 아님) | plus.kipris.or.kr |
| `DATA_GO_KR_KEY` | K-Startup 공고 수집; 권익위 API는 연결 점검만 구현 | data.go.kr |
| `BIZINFO_KEY` | 기업마당 API 연결 점검; 전체 공고 수집 미구현 | bizinfo.go.kr |
| `LAW_OC` | 법령 (비우면 시험 계정) | open.law.go.kr |

자동 제안은 비용과 검토 범위를 제한해 명시적으로 실행해요. 기본 1건, 최대 20건이며 `--idea <ID>`로 한 건을 지정할 수 있어요.

```sh
./demo.sh job trace auto --limit 1       # NAVER 뉴스·KIPRIS 특허/실용신안 검색
./demo.sh job diagnose auto --limit 1    # 원문 발췌 근거를 검증하는 P2 제안
./demo.sh job score auto --limit 1       # 기존 변화 근거에 제한한 P3 제안
```

자동 검색은 각 채널의 첫 페이지 최대 10건을 확인하는 제한 검색이에요. 발견은 사업화 확정이 아니라 담당자가 해석할 후보예요. 법인·상표·지원사업 **선정 이력**까지 자동 확인하지 않아요. 키 누락·실패는 `미실시`로 남겨요. AI 제안은 반출 허용 O급 자료만 사용하고, 기존 사람 진단·점수는 덮어쓰지 않으며 자동 승인도 하지 않아요.

## 데이터 공유

- `./demo.sh export` → `.runtime/export/bluebird_ideas_YYYYMMDD.xlsx`. 시트: 읽어주세요 / ideas / sources / contests / exclusion_reason.
  - 기본은 **외부 공유 가능 소스만**(라이선스 '제한 없음'·공공누리, 약 25,000건, 2.5MB).
  - `--include-held`를 켜면 KIPRIS·국립중앙과학관·KIDP처럼 "공개·외부 전송 보류"인 소스까지 들어가요(66,067건, 16MB, 파일 이름 `_internal`). 내부 공유용이고, 원 기관 약관 확인 전에는 밖으로 내보내지 마세요.
  - 수상자·제안자 이름은 적재할 때 이미 지웠어요. 본문에 남은 이름은 원 기관 공개본 그대로예요.
- `ideas.exclude_reasons` 열은 "뺀다면 이 이유" 후보예요(초·중·고 학생 대회, 참여예산 제안, 중복 제목 등). 걸러내지 않았으니 받는 쪽이 골라요. 뜻은 `exclusion_reason` 시트와 `docs/IDEA_POOL.md`.
- 어느 소스에서 언제 얼마나 받았는지: `docs/DATA_PROVENANCE.md` (export 때마다 다시 생성).
- 조사 기록: `docs/SOURCES.md`(공공데이터포털 전수 스캔), `docs/API_KEYS.md`(API 키·실측 스펙), `docs/REVIVAL_SOURCES.md`(성인 창업 공모 소스).

## 자주 쓰는 명령

```
./demo.sh up            # 전부 켜기
./demo.sh down          # 끄기 (데이터는 남아요)
./demo.sh status        # 서비스·DB 연결 상태 확인 (데이터 변경 없음)
./demo.sh check         # 외부 API·원본 파일 연결 점검표
./demo.sh collect       # 공식 공모전·제안 원본 수집 (분석·승인 생성 없음)
./demo.sh policy        # 소스 설정 파일(TOML)의 기록 종류·제외 후보 이유만 DB에 반영 (파일 재수집 없음)
./demo.sh export        # 공유용 xlsx(.runtime/export/) + 출처 명세(docs/DATA_PROVENANCE.md). --include-held 로 보류 소스까지
./demo.sh publish       # 이의 가져오기 → 재조명 선정 → 공개 반영
./demo.sh job <명령>     # 처리 작업 하나 실행. 예: job funnel, job kpi report
./demo.sh verify        # 회귀 시연 점검: 이의·공개 데이터를 변경하므로 일회용 환경에서만 실행
./demo.sh logs portal   # 로그 보기
```

## 개발할 때 (DB만 Docker)

코드를 고치면 바로 반영되게 하려면 DB만 Docker로 띄우고, 나머지는 직접 실행해요. Python 3.12(uv)와 Node 20 이상이 필요해요.

```
./demo.sh up db
eval "$(./demo.sh env)"          # DB 주소, 키, 경로를 현재 셸에 설정

cd pipeline && uv sync && uv run bluebird funnel     # 처리 작업
uv run python -m bluebird.api                        # 백엔드 API :8000
cd web/portal  && npm install && npm run dev         # 포털 :3000
cd web/console && npm install && npm run dev -- -p 3001   # 콘솔 :3001
```

Docker로 띄운 api, portal, console과 포트가 겹쳐요. 직접 실행할 때는 `docker compose stop api portal console`로 먼저 꺼 주세요.

테스트:

```
docker run -d --name bb-testdb -e POSTGRES_PASSWORD=t -p 55432:5432 pgvector/pgvector:pg16
cd pipeline && BB_TEST_DSN=postgresql://postgres:t@localhost:55432/postgres uv run pytest -q
uv run ruff check bluebird tests
```

테스트 DB는 일회용이어야 해요. 테스트가 DB 역할과 표본을 만들고 권한을 변경해요. 실제 시연 데이터가 있는 DB에 `BB_TEST_DSN`을 연결하지 마세요. 실행 확인만 필요하면 `./demo.sh status`를 쓰세요.

기존 데이터 유지 상태에서 코드만 갱신할 때:

```sh
docker compose build api portal console
./demo.sh job migrate --target core
docker compose up -d --no-build --wait api portal console
./demo.sh status
```

이 프로젝트는 로컬 시연용이에요. 인터넷에 공개할 인증·요청 제한·비밀키 관리·운영망 분리는 별도 운영 설계가 필요해요.

## 구성도 보기

표준 Python만으로 생성하고 미리 볼 수 있어요. 개인 경로나 전용 터미널 뷰어는 사용하지 않아요.

```sh
python3 docs/diagrams/build.py
./docs/diagrams/preview.sh       # http://127.0.0.1:8765/architecture.html
```

PDF가 필요할 때만 로컬 Chromium을 지정해요.

```sh
python3 docs/diagrams/build.py --pdf --browser /path/to/chromium
```
