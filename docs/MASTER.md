# 정제 DB 안내 (`parangsae`)

- 기준일: 2026-10-21
- 접속: PostgreSQL `161.122.152.68:5432` · DB `parangsae` · 사용자 `aix` · 접속 문자열 = `.env` `BB_DB_URL`
- 엑셀: `bluebird master xlsx --out <파일>` → 시트 `master` 1개, 141,827행 × 19열(= DB `master` 칸 그대로)
- 정리 경위: `docs/SLIM_PLAN.md` (표 8개 + 뷰 5개 → 표 3개, 마이그레이션 `master/0014`)
- 최종 파일: `bluebird master final` → `.runtime/export/final-<날짜>.xlsx` + `.json`. 사용 대상(`exclude_reasons` 빈 행)만, 16칸(제외 판단용 `exclude_reasons`·`label`·`verified` 뺌)

## 1. 구조

```
parangsae                 데이터베이스
├ public                  스키마(표를 묶는 폴더). 기본
│ ├ master                표: 최종. 1행 = 아이디어 1건       ← 이것만 보면 됨
│ ├ raw                   표: 받은 원본 그대로(master의 근거)
│ └ db_log                표: 누가·어디서·무슨 DB 작업을 했는지(추가만)
└ migrations              스키마
  └ applied               표: 적용된 구조 변경 목록(프로그램이 씀)
```

- 표 = 데이터가 행으로 저장되는 곳. 칸(열) = 표의 세로줄
- 뷰 = 이름 붙여 저장한 조회문(데이터 없음). 지금은 없음
- 모든 표·칸에 설명(COMMENT): `[출처] 설명. 만든 곳: 명령(파일)`. DBeaver = 표·칸 선택 → 속성, psql = `\d+ master`. 덤프에 같이 실림
  - 출처: `[원본]` 받은 값 · `[정제]` 규칙으로 다듬은 값 · `[계산]` 규칙으로 계산 · `[AI판정]`·`[LLM]` AI가 만든 값 · `[기록]` 작업 기록

## 2. 자주 쓰는 SQL

```sql
-- 사용 대상(제외 사유 없음): 114,781행
SELECT * FROM master WHERE exclude_reasons = '{}';

-- 유형별: product(발명·제품) · research(탐구) · policy(정책·시민 제안)
SELECT * FROM master WHERE exclude_reasons = '{}' AND item_type = 'research';

-- 제외 사유별 행 수
SELECT r, count(*) FROM master, unnest(exclude_reasons) r GROUP BY 1 ORDER BY 2 DESC;

-- 원본 보기(행별 원본 대회명 등)
SELECT m.title, r.payload FROM master m JOIN raw r ON r.source = m.api AND r.key = m.key LIMIT 10;
```

## 3. `master` 칸

| 칸 | 뜻 | 출처 | 예 |
|---|---|---|---|
| `api` | 수집 소스 id | 원본 | `seoul_budget_proposals` |
| `key` | 소스 안 레코드 번호. `api` + `key` = 행 고유값 | 원본 | `1AB-2501-0000064` |
| `title` | 제목. 글머리·접수번호 제거, 연락처·이름 가림 | 정제 | 우리 모두 함께해요!!! |
| `body` | 본문. 섹션 라벨 `[제안취지]` 등 유지, 상세 페이지 본문 이어 붙임 | 정제 | [제안내용] 현 1차로는 … |
| `kind` | 종류: 공모전 · 시민 제안 · 직원 제안 | 계산 | 시민 제안 |
| `field` | 분야(과학·발명, 주민참여예산 등) | 계산 | 주민참여예산 |
| `program` | 대회·제도명 86개. 과학·발명 4개 소스 = 원본 행 대회명(회차·연도 제거) | 계산 | 서울시 시민참여예산 |
| `award` | 수상 등급. 원본 표기 그대로(23개 소스), 없으면 빈칸 | 원본 | 장려상 |
| `year` | 제안·출품·수상 연도(수집 시점 아님) | 원본 | 2025 |
| `url` | 상세 페이지, 없으면 데이터 출처 페이지 | 원본 | https://www.data.go.kr/… |
| `exclude_reasons` | 제외 사유 코드(4장). 빈 값 = 사용 대상. 행은 지우지 않음 | 계산 | `{duplicate}` |
| `label` | AI 판정: `idea` · `idea_thin`(빈약) · `complaint`(불만뿐) · `abusive`(욕설 중심) · `off_topic`(광고·무의미). 빈칸 = 판정 안 함(이미 제외된 행) | AI판정 | idea |
| `item_type` | 유형: `product`(발명·제품·디자인·서비스) · `research`(탐구) · `policy`(정책·시민 제안) | LLM | policy |
| `goal` | 목표 한 문장. 탐구 = 알아내려는 것 | LLM | 지역 복지 네트워크를 다져 구민 복지 증진 |
| `solution` | 해결책 한 문장. 탐구 = 탐구 방법과 알아낸 결과 | LLM | 동대문구 시범 후 25개 자치구로 확대 |
| `features` | 핵심 기능 0~3개. 탐구 = 만든 장치·앱 있을 때만 | LLM | 민·관 협력, 협의체 운영 |
| `domain` | 분야 1~2개: 행정·복지·교통·환경·경제·교육·안전·문화·보건·과학기술·생활·기타 | LLM | 복지, 행정 |
| `evidence` | 해결책의 근거 원문 구절(그대로 복사) | LLM | 동대문구를 시범지역으로 … |
| `verified` | `evidence`가 제목·본문에 실제로 있음(공백 무시). 거짓 = 지어낸 값 의심 | 계산 | true |
| `embedding_input` | 벡터에 넣은 글 = 목표(끝 상투어 제거) + 해결책 + 핵심 기능. 사용 대상만 | 계산 | 시설공단의 비효율과 부패. 모든 서울시 시설공단을 통합하여 … |
| `embedding` | `embedding_input`의 벡터(OpenAI `text-embedding-3-small`, 1536차원 halfvec, 코사인 색인). 비슷한 아이디어·문제 찾기용 | LLM | – |

- `item_type`~`verified` = `label`이 `idea`인 행에만(DB가 강제)
- AI: OpenAI `gpt-4.1-mini`, 지시문 `extract-v2`(`pipeline/bluebird/extract.py`), 입력 = 제목·본문 앞 2,500자·소스 정보·대회명
- 개인정보: 전화 → `[전화]`, 이메일 → `[이메일]`, 지정 성명·팀명 → `[이름]`

## 4. 제외 사유 코드

| 코드 | 조건 | 행 |
|---|---|---:|
| `duplicate` | 같은 글(제목+본문 일치) · 같은 장소(대구, 제목+지번) · 같은 출품작(공모전, 대회·제도명+제목+수상 등급, 연도 ±1, 출처 다름)의 대표 아닌 행. `docs/DEDUP_PLAN.md` | 1,672 |
| `no_body` | 본문 내용 0자(비었거나 `[라벨]`·공백·기호뿐) | 8,452 |
| `attachment_only` | 본문 = 첨부·별첨·붙임 참조 문구뿐 | 75 |
| `title_repeat` | 본문 = 제목 반복뿐 | 70 |
| `short_title_body` | 제목 내용 5자 이하 **and** 본문 내용 10자 이하 | 32 |
| `idea_thin` | AI: 아이디어는 있으나 목표·방법을 뽑기에 너무 짧음 | 7,030 |
| `complaint` | AI: 제안 없이 불만·항의만 | 4,647 |
| `off_topic` | AI: 광고·홍보·의미 없는 글 | 158 |
| `abusive` | AI: 욕설·비방 중심 | 100 |
| `unverified` | AI 판정은 idea지만 근거 구절이 원문에 없음 | 5,406 |

- 한 행에 여러 사유 가능. 내용 글자 수 = `[라벨]`·공백·기호를 뺀 글자 수
- 사용 대상 114,781 = `exclude_reasons`가 빈 행

## 5. 현황

| 구분 | 전체 | 사용 대상 |
|---|---:|---:|
| 시민 제안 | 86,051 | 68,780 |
| 공모전 | 55,552 | 45,933 |
| 직원 제안 | 224 | 68 |
| **합계** | **141,827** | **114,781** |

| 유형(사용 대상) | 행 |
|---|---:|
| policy | 67,324 |
| product | 30,664 |
| research | 16,793 |

| 분야(사용 대상, 1행 최대 2개) | 행 |
|---|---:|
| 생활 | 41,051 |
| 과학기술 | 24,605 |
| 안전 | 23,230 |
| 복지 | 21,189 |
| 환경 | 18,660 |
| 행정 | 15,416 |
| 문화 | 14,604 |
| 교육 | 14,307 |
| 교통 | 12,549 |
| 경제 | 8,400 |
| 보건 | 7,992 |
| 기타 | 840 |

- 소스 71개, 연도 1957~2026, 본문 있음 133,384행(94%). 소스·대회별 건수 = `docs/DATA.md`

## 6. 만드는 순서

| 단계 | 명령 | 바뀌는 곳 |
|---|---|---|
| 원본 받기 | `bluebird master files` · `api` · `detail` | `raw` |
| 정제·분류 | `bluebird master refine` | `master` 기본 칸 + `kind`·`field`·`program`. 제목·본문이 바뀐 행 = AI 칸 비움 |
| 제외 사유 | `bluebird master reasons` | `exclude_reasons` |
| AI 판정·가공 | `bluebird master extract` (사유 없는 행 중 판정 전만) | `label`~`verified` |
| 제외 사유(AI 반영) | `bluebird master reasons` | `exclude_reasons` |
| 벡터 | `bluebird master embed` (사용 대상 중 글이 바뀐 행만) | `embedding_input`·`embedding` |

- 외부 호출(크롤링·AI) 기록 = 실행한 PC의 `.runtime/egress-YYYY-MM.jsonl`(git 제외, DB 아님). 보낸 값 원문 없음(칸 이름·sha256만)
- 남은 문제: 국민신문고 상세 본문 477행(API 키 필요), 재제출 중복 2단계(사람 표시 대기), 본문 속 일반 이름 미가림

## 7. DB 작업 기록(`db_log`)

DB를 쓰는 쪽끼리(로컬·서버, git 공유 여부 무관) 무엇을 했는지 확인하는 표. 덤프에 같이 실려 간다. **추가만**(수정·삭제·TRUNCATE = DB가 거부). 같은 규칙이 DB 주석(`COMMENT ON TABLE db_log`)에도 있어 git 없는 쪽도 본다.

| 칸 | 내용 | 규칙 |
|---|---|---|
| `at` | 작업 시각 | 기본 = 기록 시각. 지난 일을 나중에 적을 때만 지정 + note에 `(시각 추정: <근거>)` |
| `place` | 어디서 | 소문자·숫자·`-_` (`local`, `server`). 기계마다 고정 = `.env` `BB_LOG_PLACE` |
| `action` | 작업 | `dump` · `restore` · `drop` · `note` = 직접. `migrate` · `files` · `api` · `detail` · `refine` · `reasons` · `fill`(= `extract`, note 앞에 `extract <지시문 버전> <모델>`) = 자동 |
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
