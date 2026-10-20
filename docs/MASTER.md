# master 표 안내(공유용)

- 기준일: 2026-10-15 (상세 본문 수집 2026-10-15)
- 파일: `master-<날짜>.xlsx` (시트 `master`, 141,827행 × 21열 = DB `master` 칸 + 대회·제도 이름 3칸)
- DB 접속: PostgreSQL `161.122.152.68:5432` · DB `parangsae` · 사용자 `aix` · 접속 문자열 = `.env` `BB_DB_URL` · 표 `public.master`(정제본), `public.raw`(받은 그대로)
- 만들기: `bluebird master xlsx --out .runtime/export/master-<날짜>.xlsx` (모든 칸 = 텍스트·숫자, 수식 없음)
- 원본 DB: `parangsae` → `public.master`
- 전처리 상세: `docs/PREPROCESS.md`

## 1. 한눈에 보기

- 공모전 출품작·시민제안 71개 소스 → 표 1개로 통합
- 1행 = 아이디어(제안·출품작) 1건
- 원본 필드(제목·본문 등) + LLM 생성 필드(키워드·문제·기능·대상·분야)

| 구분 | 값 |
|---|---:|
| 전체 행 | 141,827 |
| 소스 | 71 |
| 본문 있음 | 133,384 (94%) |
| 연도 범위 | 1957 ~ 2026 |

## 2. 필드 설명

| 필드 | 이름 | 출처 | 형식 | 설명 | 예 |
|---|---|---|---|---|---|
| `api` | 수집 소스 | 원본 | 텍스트 | 데이터 출처 id | `seoul_budget_proposals` |
| `key` | 원본 키 | 원본 | 텍스트 | 소스 안 레코드 번호. `api` + `key` = 행 고유값 | `1AB-2501-0000064` |
| `title` | 제목 | 원본(정제) | 텍스트 | 아이디어 제목. 글머리·접수번호 제거 | 교차로 통행 개선 |
| `body` | 본문 | 원본(정제) | 텍스트 | 아이디어 내용. 섹션 라벨 `[제안취지]` 등 유지, 줄바꿈 → 공백 | [제안내용] 현 1차로는 … |
| `contest` | 공모전명 | 원본 또는 LLM | 텍스트 | 공모전·대회·제도명. 빈 값 있음 | 전국과학전람회 |
| `origin` | 공모전명 출처 | 표시 | `O` / `X` | `O` 원본 값, `X` LLM 값, 빈칸 = 공모전명 없음 | O |
| `award` | 수상 등급 | 원본 | 텍스트 | 원본 행의 수상 필드 값 그대로(23개 소스). 등급외·선정·기타 등 원본 표기 유지. 수상 필드 없는 소스 = 빈칸 | 장려상 |
| `url` | 링크 | 원본 | URL | 상세 페이지 또는 데이터 출처 페이지 | https://www.data.go.kr/… |
| `year` | 연도 | 원본 | 숫자 | 제안·출품·수상 연도(수집 시점 아님) | 2025 |
| `fetched` | 수집 시각 | 원본 | 날짜시각 | 우리가 데이터를 받은 시각(KST) | 2026-10-14 15:39 |
| `keyword` | 키워드 | LLM | 쉼표 목록 | 대표 키워드 2~3개 | 교통, 교차로, 좌회전 |
| `problem` | 문제 | LLM | 텍스트 | 해결하려는 문제 한 문장. 근거 없으면 빈칸 | 좌회전 차로가 1개뿐이라 … |
| `feature` | 기능·방법 | LLM | 텍스트 | 제안의 핵심 기능·방법 한 문장. 근거 없으면 빈칸 | 2차선까지 좌회전 동시 신호 … |
| `target` | 대상 | LLM | 텍스트 | 주 수혜·사용 대상. 근거 없으면 빈칸 | 운전자 |
| `domain` | 분야 | LLM | 쉼표 목록 | 고정 11개 중 1개 이상 | 교통, 안전 |
| `exclude_reasons` | 전처리 사유 | 계산 | 코드 목록 | 전처리에서 걸린 사유(`exclusion_reason` 표, 아래 목록). 빈 목록 = 해당 없음. 행 삭제 없음 | duplicate |
| `canonical_api` · `canonical_key` | 대표 행 | 계산 | 텍스트 | 중복일 때 대표 행의 `api`·`key`. 규칙 = `docs/DEDUP_PLAN.md` | kipris_idea_api · h:360c… |
| `program_id` (엑셀: `kind`·`field`·`program`) | 대회·제도 | 계산 | `program` 표 | 종류(공모전·시민 제안·직원 제안) · 분야 · 대회·제도 이름. 규칙 = `pipeline/bluebird/programs.py` | 공모전 · 과학·발명 · 전국과학전람회 |

- `domain` 값: 행정, 복지, 교통, 환경, 경제, 교육, 안전, 문화, 보건, 과학기술, 기타
- LLM: OpenAI `gpt-4.1-mini`, 입력 = 제목·본문(앞 2,500자)·소스 정보
- 개인정보: 전화 → `[전화]`, 이메일 → `[이메일]`, 지정 성명·팀명 → `[이름]`
- 중복 제외 조회: `WHERE NOT 'duplicate' = ANY(exclude_reasons)` (1,671행 제외 → 140,156행). 사유 없는 행 = `exclude_reasons = '{}'` (132,122행)

### 전처리 사유 코드 (중복 제외 행 기준 건수)

| 코드 | 조건 | 행 |
|---|---|---:|
| `duplicate` | 같은 글·같은 장소·같은 출품작의 대표 아닌 행 (`docs/DEDUP_PLAN.md`) | 1,671(전체) |
| `no_body` | 본문 내용 0자 (비었거나 `[라벨]`·공백·기호뿐) | 7,859 |
| `attachment_only` | 본문 = 첨부·별첨·붙임 참조 문구뿐 | 75 |
| `title_repeat` | 본문 = 제목 반복뿐 | 70 |
| `short_title_body` | 제목 내용 5자 이하 **and** 본문 내용 10자 이하 | 31 |
| `idea_thin` · `complaint` · `abusive` · `off_topic` | AI 판정(`quality.idea_label`): 빈약 · 불만뿐 · 욕설 중심 · 광고·무의미 | 판정 전 |

- 내용 글자 수 = `[라벨]`·공백·기호를 뺀 글자 수

### `quality` 표 (master 1행 = 1행, `bluebird master reasons`가 매번 재계산)

| 칸 | 뜻 | 제외 조건 |
|---|---|---|
| `title_len` · `body_len` | 제목·본문 내용 글자 수 | `short_title_body`·`no_body`에 사용 |
| `attachment_only` · `title_repeat` | 위 사유와 같음 | 예 |
| `hangul_ratio` | 본문 내용 중 한글 비율 | 아니오(표시만) |
| `has_profanity` · `has_repeat` | 욕설 단어 · ㅋㅋㅋㅋ/!!!! 반복 | 아니오(표시만: 단어 규칙 오탐 많음 → AI 판정 참고용) |
| `idea_label` · `idea_reason` · `idea_model` · `idea_at` | AI 판정 결과(재계산 때 유지) | `idea` 아니면 그 값이 사유 |

- 엑셀: `title_len`·`body_len`·`flags`(profanity·repeat·low_hangul)·`idea_label`

## 3. 필드별 채움 현황

| 필드 | 채워진 행 | 비율 |
|---|---:|---:|
| `title` | 141,827 | 100% |
| `body` | 133,384 | 94% |
| `contest` | 107,230 | 76% |
| `award` | 52,956 | 37% |
| `url` | 141,827 | 100% |
| `year` | 141,390 | 99.7% |
| `keyword` | 141,827 | 100% |
| `problem` | 97,665 | 69% |
| `feature` | 112,456 | 79% |
| `target` | 111,109 | 78% |
| `domain` | 141,827 | 100% |

## 4. 주요 소스

| 소스 | 내용 | 행 | 본문 있음 |
|---|---|---:|---:|
| `kipris_idea_api` | KIPRIS 학생 발명·과학 아이디어 | 38,563 | 38,563 |
| `seoul_budget_proposals` | 서울 시민참여예산 제안 | 28,811 | 28,811 |
| `seoul_free_suggestions` | 상상대로 서울 자유제안 | 20,138 | 20,137 |
| `acrc_open_proposals` | 국민신문고 공개제안 | 8,996 | 8,519 |
| `daegu_budget_project_proposals` | 대구 주민참여예산 제안 | 7,706 | 7,704 |
| `gwangju_budget_proposals` | 광주 주민참여예산 | 5,986 | 5,986 |
| `gyeonggi_budget_proposals` | 경기 주민참여예산 | 4,135 | 4,126 |
| `science_invention_archive_2015_onward` | 학생과학발명품경진대회 출품작 | 3,300 | 3,296 |
| `science_exhibition_archive_2015_onward` | 전국과학전람회 출품작 | 3,267 | 3,266 |
| `ulsan_budget_proposals` | 울산 주민참여예산 | 3,046 | 2,734 |
| 나머지 61개 | 지자체 참여예산·공공기관 공모전 등 | 17,879 | – |

## 5. 문제점과 계획

| # | 문제 | 현황 | 계획 | 상태 |
|---|---|---|---|---|
| 1 | 공모전명 빈 값 | 34,597행(24%) 빈칸. 원본·소스 정보 모두 대회명 없음. 대부분 시민제안·참여예산(국민신문고 8,535, 대구 7,706, 광주 5,913, 울산 3,026) | 당분간 유지. `origin`으로 원본·LLM 구분 | 보류 |
| 2 | 중복 | 완전 일치 3기준(제목+본문 · 제목+지번 · 같은 출품작) → 1,671행 `duplicate` 표시. 상세 `docs/DEDUP_PLAN.md` | 본문 일부 수정·제목만 바꾼 재제출 = 2단계(표본 표시 대기) | 1단계 완료 |
| 3 | 본문 없음 | 원본 사이트 상세 크롤링으로 19,978행 확보. 남은 7,850행(중복 제외) = `no_body` 표시 | 남은 소스 = 원본에 공개 본문 없음(창업경진 예선 1,938·거제 1,199·KAIA 550·세종 448·제주 440 등). 국민신문고 477 = API 키 필요 | 1단계 완료 |
| 4 | 국민신문고 성격 | 제안 외 민원·항의 글 섞임 | 소스 전체 제외 검토 | 보류 |
| 5 | LLM 결과 품질 | 새 본문 19,329행이 제목만 보고 채운 값. 본문 2,500자 초과 2,713행 앞부분만 반영 | 대상 34,461행 재생성(`docs/PREPROCESS_PLAN.md` 4장) | API 키 대기 |
| 6 | 연도 없음 | 431행(중복 제외). 전남 우수제안·6차산업 247행 채움 | 남은 소스 = 원본에 날짜 칸 없음 | 완료 |
| 7 | 웹 크롤링 의존 | 상세 페이지 수집 소스: 서울 자유제안·디자인진흥원 3·과학관 아카이브 2·광주·경기·울산·유성 참여예산. 페이지 구조 바뀌면 깨짐 | API·파일 대체 수단 확인 | 보류 |
| 8 | 본문 속 이름 | 일반 문장 속 이름 미가림 | 추가 가림 안 함. 필요 시 LLM으로 처리 | 보류 |

- 짧은 제목(5자 이하 3,406행): 제외하지 않음("우유병"처럼 의미 있는 경우 있음)

## 6. DB 작업 기록(`db_log`)

DB를 쓰는 쪽끼리(로컬·서버, git 공유 여부 무관) 무엇을 했는지 확인하는 표. 덤프에 같이 실려 간다. **추가만**(수정·삭제·TRUNCATE = DB가 거부). 같은 규칙이 DB 주석(`COMMENT ON TABLE db_log`)에도 있어 git 없는 쪽도 본다.

| 칸 | 내용 | 규칙 |
|---|---|---|
| `at` | 작업 시각 | 기본 = 기록 시각. 지난 일을 나중에 적을 때만 지정 + note에 `(시각 추정: <근거>)` |
| `place` | 어디서 | 소문자·숫자·`-_` (`local`, `server`). 기계마다 고정 = `.env` `BB_LOG_PLACE` |
| `action` | 작업 | `dump` · `restore` · `drop` · `note` = 직접. `migrate` · `files` · `api` · `detail` · `refine` · `fill` · `reasons` · `classify` = 자동 |
| `note` | 내용 | 아래 형식, 한 줄, 빈 값 불가 |
| `master` · `raw` | 기록 시점 행 수 | 자동 |
| `file` · `sha256` | 덤프 파일 | `dump` = 파일 이름 필수(sha256 비움). `restore` = 둘 다 필수 |

### note 형식

| action | 형식 | 예 |
|---|---|---|
| `dump` | `<DB> 전체 pg_dump(<버전>) → <압축·분할> → <전달 경로>` | `parangsae 전체 pg_dump(16.13) → xz → 7z 5분할 → 메일` |
| `restore` | `<파일> → <DB 이름>(<호스트>). 확인: sha256·행 수 <일치/불일치>` | `parangsae-2026-10-16.dump.xz → parangsae(로컬 Docker). 확인: sha256·행 수 일치` |
| `drop` | `<대상> 삭제. 이유: <이유>. 백업: <파일 또는 없음>` | `bluebird_master 삭제. 이유: parangsae에 전부 포함. 백업: bluebird_master-2026-10-15.dump.xz` |
| `note` | `<한 일>. 이유: <이유>` · 정정 = `정정 #<id>: <바른 내용>` | `정정 #3: 복원 파일 = bluebird_master-2026-10-15.dump.xz` |
| 자동 | 옵션 + 소스별 상태·숫자 | `--only kipris_idea_api kipris_idea_api ok rows=38563` |

- 공통: 숫자는 쉼표 없이, 같은 일을 두 번 적지 않음, 틀리면 고치지 말고 `정정` 새 행

### 이관 순서

1. 보내는 쪽: `bluebird master log --action dump --file <만들 파일 이름> --note "<형식>"` **먼저** → `pg_dump` (그래야 이 행이 덤프에 실림)
2. 받는 쪽: 새 이름 DB로 복원(기존 DB 덮어쓰지 않음)
3. 받는 쪽: `bluebird master log --action restore --file <받은 파일> --note "<형식>"` (sha256 자동. 파일이 없으면 `--sha256`)
4. 받는 쪽: `bluebird master log --merge-from <기존 DB 접속 문자열>` → 기존 DB에만 있던 기록을 새 DB로 옮김(같은 행 = 시각·장소·작업·내용)
5. 받는 쪽: 기존 DB 정리 후 `--action drop`

### 코드 없이 SQL로 적기

```sql
INSERT INTO db_log (place, action, note, master, raw, file, sha256)
VALUES ('server', 'restore', '<파일> → parangsae(서버). 확인: sha256·행 수 일치',
        (SELECT count(*) FROM master), (SELECT count(*) FROM raw), '<파일>', '<sha256>');
SELECT * FROM db_log ORDER BY at;   -- 보기
```

- 0008 이전 이력(2026-10-14 로컬 생성 ~ 2026-10-19 로컬 복원) = 마이그레이션 `master/0008_db_log.sql`, 규칙 = `master/0009_db_log_rules.sql`
