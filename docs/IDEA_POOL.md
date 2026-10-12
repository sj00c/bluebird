# 아이디어 선별 재료 (제외 후보 이유)

작성 2026-10-12. 파랑새 DB의 아이디어 66,067건을 하나씩 세어 성격을 나눈 결과와, 그 결과를 DB에 어떻게 담았는지.

**원칙: 걸러내지 않는다.** 66,067건 전부가 깔때기·카드·공개 작업을 그대로 거친다. 대신 아이디어마다 "뺀다면 이 이유로"를 구조화된 필드로 쌓아 두고, 어떤 이유를 실제로 적용할지는 사람이 나중에 고른다.

## 1. 측정

DB에는 아이디어가 총 67,199건 들어 있고, 출처에서 사라져 사용 중단 처리된 1,132건을 빼면 실제 쓰는 건 66,067건이다. 이걸 출처별로 전부 세어 성격을 나눴다.

| 성격 | 건수 | 비율 | 본문(설명글) 있음 |
|---|---|---|---|
| 초·중·고 학생 과학·발명 대회 (KIPRIS 1979~2014 + 국립중앙과학관 2015~) | 35,589 | 54% | 26,418 |
| 주민참여예산·시민제안 | 22,464 | 34% | 77 |
| 디자인 공모 (굿디자인·청년디자인·공공디자인) | 5,726 | 9% | 131 |
| 창업·데이터 활용 경진대회 | 2,396 | 4% | 365 |
| 직원 개선제안 | 223 | 0.3% | 43 |
| 그 외 공모전 (6차산업·소방·행복농촌·KAIA 등) | 1,160 | 2% | 349 |

파랑새의 질문 "이 수상 아이디어가 왜 사업이 안 됐고, 지금 다시 해볼 만한가"를 바로 던질 수 있는 건 창업·데이터 경진 + 그 외 공모전 ≈ 3,500건(5%). 나머지는 중학생 과학전람회 작품이거나 "우리 동네 보도블럭 교체" 같은 행정 제안이다. 하지만 "이거 예전에 이미 나온 아이디어 아닌가"를 잡는 비교 자료로는 전부 쓸모가 있다.

KIPRIS Plus API(38,563건)도 들여다봤는데 1965~2014 학생 대회가 98%라 추가로 받지 않는다. 자세한 건 `docs/API_KEYS.md`.

## 2. DB에 담은 것

### 사실 (어디서 왔고 무엇인가)

| 필드 | 위치 | 값 | 어떻게 채우나 |
|---|---|---|---|
| 기록 종류 `record_kind` | 출처 (`core.source`) | 수상작 / 출품작 / 국민·주민 제안 / 직원 개선제안 | 출처 설정 파일(TOML)에 필수 기입 |
| 대회 대상자 `audience` | 대회 (`core.contest`) | 초·중·고 학생 대회 / 일반 / 미확인 | 대회 이름 규칙으로 초기화(학생·청소년·초등·과학전람회·발명품경진 등, '대학생'은 제외) → 사람이 고침 |
| 정규화 제목 `norm_title` + 같은 제목 묶음 `core.idea_dup` | 아이디어 | 공백 지우고 소문자로 같은 제목이면 한 묶음, 대표 1건 | 재계산 함수 |
| 소스 편집 판단 `exclude_reason` | 출처 | 상품화 뒤 받는 인증 / 기관 내부 활동 / 수업 사례 | TOML에 선택 기입 |

### 제외 후보 이유 (`core.idea_exclusion`)

위 사실들에서 아이디어마다 "뺀다면 이 이유"를 한 줄씩 쌓는다. 한 아이디어에 이유가 여러 개 붙을 수 있다. 이유 어휘는 `core.exclusion_reason` 표에 있다.

| 이유 코드 | 뜻 | 근거 | 현재 건수 |
|---|---|---|---|
| `student_contest` | 초·중·고 학생 대회 | 대회 대상자 | 35,589 |
| `public_proposal` | 참여예산·국민/주민 제안 (공모전이 아님) | 기록 종류 | 22,464 |
| `duplicate_title` | 같은 제목이 이미 있음 (대표 1건은 제외) | 제목 묶음 | 2,574 |
| `certified_product` | 상품화 뒤 받는 인증 (굿디자인) | 출처 편집 판단 | 2,415 |
| `improvement_proposal` | 직원 개선제안 | 기록 종류 | 223 |
| `internal_activity` | 기관 내부 활동 사례 (품질분임조·적극행정) | 출처 편집 판단 | 112 |
| `teaching_case` | 수업·교육 사례 | 출처 편집 판단 | 6 |

이유가 하나도 없는 아이디어: **5,197건**. 이유 1개 58,357건, 2개 2,513건.

규칙으로 붙인 행(`decided_by='rule'`)은 재계산할 때마다 새로 쓰고, 사람이 넣은 행(`decided_by`에 사람 식별자)은 그대로 남는다.

### 공개용 DB

`publish.idea`에 `record_kind`·`audience`·`exclude_reasons`(이유 코드 배열) 세 열이 같이 나간다(템플릿 v3). 포털이든 벌크 내려받기든 받는 쪽이 고를 수 있다.

## 3. 운영

- 출처 설정 파일(`deploy/local/*.toml`)의 `record_kind`·`exclude_reason`이 기준. 바꾸고 `./demo.sh policy`를 실행하면 파일 재수집 없이 DB에 반영되고 선별 재료(학생 표시·제목 묶음·이유)가 다시 계산된다.
- 대회가 학생 대회인지 틀렸으면 `core.contest.audience`를 직접 고치고 `./demo.sh policy`. 사람이 고친 값은 규칙이 덮어쓰지 않는다. 지금 대회 677개 중 120개가 학생 대회로 표시됐고 557개는 '미확인'.
- 특정 아이디어에 이유를 직접 붙이려면 `INSERT INTO core.idea_exclusion (idea_id, reason, decided_by) VALUES (..., 'internal_activity', '이름')`.
- 새 이유가 필요하면 `core.exclusion_reason`에 코드를 추가하는 마이그레이션을 쓴다.

## 4. 벌크로 뽑을 때

```sql
SELECT i.id, s.id AS source, s.record_kind, c.name AS contest, c.audience, i.year, i.award, i.title, i.body,
       ARRAY(SELECT x.reason FROM core.idea_exclusion x WHERE x.idea_id = i.id ORDER BY 1) AS exclude_reasons
  FROM core.idea i
  JOIN core.contest c ON c.id = i.contest_id
  JOIN core.source  s ON s.id = i.source_id
 WHERE i.retired_at IS NULL
 ORDER BY i.id;
```

이유 배열이 비어 있으면 지금까지 찾은 어떤 제외 근거에도 걸리지 않은 아이디어다. 어떤 이유를 뺄지는 받는 쪽에서 `exclude_reasons && ARRAY['student_contest', ...]` 로 고른다.

## 5. 아직 안 한 것 (의도적으로)

- 어떤 이유를 실제 제외로 쓸지 정하지 않았다. 깔때기·카드·포털에는 지금 66,067건이 다 들어간다.
- 대회 557개의 '미확인'을 사람이 훑지 않았다.
- 대한민국디자인전람회 1,257건은 이유가 안 붙어 있다(사업화 추적에 맞는지 샘플 보고 정할 것).

---

## 부록: DB 변경문 (개발용)

- `0011_record_kind_audience.sql` — `core.source.record_kind`, `core.contest.audience` + `core.contest_audience(name)`, `core.idea.norm_title`, `core.idea_dup` + `core.refresh_idea_dup()`
- `0012_idea_exclusion.sql` — `core.exclusion_reason`(어휘), `core.source.exclude_reason`, `core.idea_exclusion` + `core.refresh_idea_exclusion()`
- 깔때기(`core.funnel_stage`)·카드·흔적·공개 쿼리는 바뀌지 않았다. 어느 것도 이 표들을 조건으로 쓰지 않는다.
