# 정제 DB 정리: master 하나로 (확정 2026-10-21)

목표 = `master` 한 표만 보면 원하는 값(정제 글 + 제외 사유 + AI 판정·가공)이 다 있음. 행은 지우지 않음.

## 1. 결과 구조

| 스키마 | 표 | 내용 |
|---|---|---|
| `public` | `raw` | 받은 원본 그대로 |
| `public` | `master` | 최종. 아래 칸 |
| `public` | `db_log` | 작업 기록 (팀원 것, 그대로) |
| `migrations` | `applied` | 적용된 구조 변경 목록 (프로그램이 씀, 그대로) |

뷰 = 없음. 표 8개 + 뷰 5개 → 표 3개.

## 2. master 칸

| 칸 | 내용 | 어디서 |
|---|---|---|
| `api`, `key` | 소스, 원본 번호 | 그대로 |
| `title`, `body` | 제목, 본문(정제) | 그대로 |
| `kind`, `field`, `program` | 종류(공모전/시민 제안/직원 제안), 분야, 대회·제도명 | `program` 표에서 옮김 |
| `award`, `year`, `url` | 수상 등급, 연도, 원문 링크 | 그대로 |
| `exclude_reasons` | 제외 사유 코드. 빈 값 = 쓸 행 | 그대로 |
| `label` | AI 판정: idea / idea_thin / complaint / abusive / off_topic | `quality.idea_label` |
| `item_type`, `goal`, `solution`, `features`, `domain`, `evidence`, `verified` | AI 가공(유형·목표·해결책·기능·분야·근거·근거 확인) | `idea_fields` |

쓸 행 = `WHERE exclude_reasons = '{}' AND verified`.

## 3. 지우는 것

| 지우는 것 | 역할은 어디로 |
|---|---|
| `idea_fields` 표 | master 칸. `extract`가 master에 바로 씀 |
| `quality` 표 | AI 판정 = `master.label`. 글자 수 = `reasons` 실행 중 계산만. 욕설·반복·한글 비율 표시 = 버림 |
| `program` 표 | master `kind`·`field`·`program`. `refine`이 원본 대회명으로 바로 계산 → `classify` 명령 삭제 |
| `exclusion_reason` 표 | 코드 9개 뜻 = `master.exclude_reasons` 칸 설명 |
| `egress_call` 표 | DB 밖: 실행한 PC의 `.runtime/egress-YYYY-MM.jsonl`(git 제외) |
| 뷰 5개 | 없앰 |
| master `keyword`·`problem`·`feature`·`target`·옛 `domain` | 옛 AI 값 → 새 AI 값으로 대체 |
| master `contest`·`origin` | 대회명 = `program`. 행별 원본 대회명 = `raw` |
| master `canonical_api`·`canonical_key` | 중복 여부 = `exclude_reasons`의 `duplicate` |
| master `fetched`·`program_id` | 받은 시각 = `raw.fetched`, 번호 → 글자 |
| `fill`·`classify` 명령 | `extract`·`refine`이 대신 |

## 4. 바뀌는 동작

- 중복 "같은 출품작"의 대회명 = `program`(공모전 행만)
- `refine`이 제목·본문을 바꾼 행 = AI 칸 비움 → 다음 `extract`가 다시 판정
- 실행 순서: `detail` → `refine` → `reasons` → `extract` → `reasons`

## 5. 미리 확인한 결과 (로컬 사본)

- 대회·제도 분류를 원본 대회명만으로 다시 계산: 141,827행 전부 지금과 같음
- 중복(`program` 기준, 공모전만): 지금 1,671행과 같고 1행 추가
  - `science_museum_awards` 228 = `science_exhibition_archive_2015_onward` 423:30465 (같은 제목, 2023 전국과학전람회 특상). 아카이브 행에 대회명이 없어 지금은 못 찾던 것
  - 공모전만 쓰는 이유: 시민 제안까지 넣으면 대구 참여예산 제안·선정 목록 199행이 새로 묶임(규칙 의도 = 공모전 출품작)

## 6. 순서

1. `master/0014`: 새 master 만들기 → 값 옮기기 → 옛 표·뷰 삭제 → 설명
2. 코드·테스트·문서
3. 로컬 사본에서 실행 → 옮긴 값 해시 비교, `refine`·`reasons` 다시 돌려 값 유지 확인
4. 서버 적용 → 로컬과 해시 비교 → `db_log`
