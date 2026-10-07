# 파랑새 (Bluebird)

공모전 수상 아이디어를 모아서 다음 내용을 정리해 보여 주는 서비스예요.

- 그 아이디어가 왜 사업이 안 됐는지
- 그 뒤로 무엇이 바뀌었는지
- 지금 다시 해볼 만한지

모든 판정에는 근거 URL이 붙어요. 사람이 승인한 것만 공개돼요.

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

## 처음 띄우기 (팀원용)

필요한 건 **Docker Desktop** 하나예요.

1. 원본 데이터를 받아서 레포 안에 둬요.
   - 원본 데이터는 git에 없어요. 수상자 이름이 들어 있어서 따로 전달해요.
   - 넣을 위치는 아래와 같아요.

   ```
   reference/parangsae-src/     # 인수인계 패키지 (parangsae-src.zip 압축 해제)
   data/opendata/design_idea.csv
   data/opendata/catalog.csv
   ```

2. 아래 명령을 차례로 실행해요.

   ```
   ./demo.sh init      # .env, 익명화 키, 콘솔 로그인 토큰, 원본 파일 준비 (처음 한 번)
   ./demo.sh cycle     # 빌드 → 적재 → 카드 → 소스 점검 → 공개 → 화면 띄우기
   ./demo.sh tokens    # 콘솔 로그인 토큰 보기 (reviewer1 등)
   ```

   - `cycle`은 처음 한 번 5~10분 걸려요. 아이디어가 약 3만 건이에요.
   - 끝나면 포털과 콘솔 주소가 출력돼요.

## API 키 넣기

`.env`에 키를 넣고 `./demo.sh cycle`을 다시 돌리면 돼요. 키가 없는 소스는 `key_required`로 표시만 되고, 나머지는 정상으로 동작해요.

| 키 | 채워지는 것 | 발급 |
|---|---|---|
| `OPENAI_API_KEY` 또는 `ANTHROPIC_API_KEY` | 원인 진단, 카드 요약 | 각 사이트 |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 사업화 흔적: 후속 보도 | developers.naver.com |
| `KIPRIS_PLUS_KEY` | 사업화 흔적: 특허·상표 | plus.kipris.or.kr |
| `DATA_GO_KR_KEY` | K-Startup 공고 매칭, 권익위 국민제안 | data.go.kr |
| `BIZINFO_KEY` | 기업마당 공고 | bizinfo.go.kr |
| `LAW_OC` | 법령 (비우면 시험 계정) | open.law.go.kr |

어떤 소스가 실제로 연결되는지는 `./demo.sh check`로 확인해요.

## 자주 쓰는 명령

```
./demo.sh up            # 전부 켜기
./demo.sh down          # 끄기 (데이터는 남아요. 데이터까지 지우려면 docker compose down -v)
./demo.sh check         # 외부 API·원본 파일 연결 점검표
./demo.sh job <명령>     # 처리 작업 하나 실행. 예: job funnel, job kpi report, job trace auto
./demo.sh verify        # 데모 동작 점검 (실패 0이어야 해요)
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
