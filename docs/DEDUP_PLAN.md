# master 중복 처리 (적용됨 2026-10-15)

대상: 서버 `parangsae.public.master` 141,827행. 임계값 없음, **완전 일치만** 중복. 제목만 같음 = 중복 아님.

## 1. 규칙

| 규칙 | 조건 | 대표 | 대표 외 |
|---|---|---|---:|
| 같은 글 | 제목 + 본문 완전 일치(공백만 제거). 대구 참여예산 제외 | 먼저 낸 것 | 337 |
| 같은 장소 | 제목 + 지번 완전 일치 | 나중 것 | 75 |
| 같은 출품작 | 대회명 + 제목 + 수상 등급 일치, 연도 차 1년 이내, 출처 다름 (한 작품이 여러 출처에 실린 것) | 본문 긴 것 | 1,149 |
| 합계 | | | 1,561 |

- 제목 정규화 = 글자·숫자만 소문자, 대회명 = 회차·연도·공백 제거
- 지번 = 원본 `사업 지번주소`(현재 대구 참여예산만 있음). 대구는 본문이 정형 문구 → 같은 글 대신 같은 장소로 판단
- 먼저/나중 = 원본 날짜 칸(서울 `WRITE_DT`·`REG_DATE`·`RDATE`, 국민신문고 `regDate`, KIPRIS `openingDate`, 세종 `등록일시`, 울산 `등록일`), 없으면 `year`. 동률 = `api` → `key`
- 순서: 같은 글 → 같은 장소 → 같은 출품작. 뒤 단계는 앞 단계 대표끼리. 중복 행은 최종 대표를 가리킴

## 2. 저장 (PostgreSQL)

| 객체 | 내용 |
|---|---|
| `master.exclude_reasons` | text[]. 전처리 사유 코드. `{}` = 해당 없음 |
| `master.canonical_api` · `canonical_key` | 중복일 때 대표 행. `master(api, key)` 참조 |
| `exclusion_reason` | 사유 코드 뜻·규칙 (`duplicate`) |

- 행 삭제 없음. 계산 = `bluebird master reasons` (refine 다음, 매번 전체 재계산. `no_body` 사유도 같이 계산)
- 마이그레이션 `master/0004_exclusion.sql`·`0005`·`0007`, 코드 `pipeline/bluebird/dedup.py`

```sql
SELECT * FROM master WHERE exclude_reasons = '{}';                  -- 전처리 통과
SELECT * FROM master WHERE NOT 'duplicate' = ANY(exclude_reasons);  -- 중복만 제외
SELECT m.title, c.title AS 대표 FROM master m
  JOIN master c ON (c.api, c.key) = (m.canonical_api, m.canonical_key);
```

## 3. 검증 결과

- 로컬 사본 → 서버 순 적용. 규칙별 수치 = 사전 계산과 동일
- 재실행 결과 동일 · 대표가 다시 중복인 행 0

보류: 본문 일부 수정 재제출(582행) · 제목만 바꾼 재제출(181행) — 기준선 필요, 2단계
