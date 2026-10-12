# 서울 열린데이터광장 OpenAPI 전수 확인 (적재 전 사전조사)

목표: 나중에 DB(core.idea)에 넣고 AI(카드·임베딩·유사도)를 돌릴 수 있게, 서울시가 데이터를 **어떻게 주는지**를 확정한다.
확인일 2026-10-12. 키 `SEOUL_OPENAPI_KEY`로 22종 전량 수집. DB 적재·`sources.toml` 반영은 아직 안 함(승인 후).

| 파일 | 내용 |
|---|---|
| `data/seoul/raw/{SERVICE}.jsonl` | API 원본 전량(약 136MB). `_manifest.json` 건수·시각, `_profile.json` 필드별 채움률·길이 |
| `data/seoul/spec/{SERVICE}.json` | **공식 명세**(필드 한글 설명·요청 필터·라이선스·갱신주기·제공부서) + 실측 통계 |
| `data/seoul/files/` | 공식 첨부파일·Sheet CSV 비교본 |

---

## 1. 제공 방식 (채널 3개, API JSON이 정답)

| 채널 | 실제 동작 | 판정 |
|---|---|---|
| **OpenAPI** `openapi.seoul.go.kr:8088/{KEY}/json/{SERVICE}/{s}/{e}/[필터]` | 1회 최대 1,000건(초과 `ERROR-336`), 범위 밖 `INFO-200`, 키 오류는 json 요청에도 XML `INFO-100`. 순서 안정, 22종 1분 내 수집, 호출 제한 안 걸림 | **사용**. 원문 그대로(UTF-8, 줄바꿈 보존) |
| Sheet 내려받기(CSV) | 접수정보 1파일 37.6MB, 28,811행·35열(한글 헤더), 분할 필드 그대로 | **사용 안 함.** CP949라 `·` 등이 `?`로 깨지고 줄바꿈 제거됨(사업내용1이 1,000→983자) |
| 첨부파일 | DB형은 대부분 없음. `civilBudRec`·창업경진 2종만 있음 | 갱신 확인용 |

- 요청 필터(공식): 접수·선정 `FIS_YEAR`, 자유제안 `TITLE`, 엠보팅 `VOTE_NO`·`VOTE_SJ`, 창업경진 `YR`, 서울연구원 `SEQ_SE`. 나머지는 필터 없음(`civilBudRec`은 연도 넣어도 무시)
- 공식 명세 원문: `https://data.seoul.go.kr/dataList/openApiView.do?infId={OA}&srvType=A`

## 2. 공식 메타 (라이선스·갱신주기)

| 서비스 | OA | 라이선스 | 갱신 | 제공부서 |
|---|---|---|---|---|
| `bizSuggAcceptInfo` | OA-15412 | 제한 없음 | 수시 | 기획조정실 재정기획관 재정담당관 |
| `bizSuggSelectionInfo` | OA-15414 | 제한 없음 | 수시 | 기획조정실 재정기획관 재정담당관 |
| `bizSuggExecutionInfo` | OA-15413 | 제한 없음 | 수시 | 기획조정실 재정기획관 재정담당관 |
| `civilBudRec` | OA-23096 | 공공누리 0유형 : 자유이용 (출처미표기) | 연간 | 기획조정실 재정기획관 재정담당관 |
| `BizInter2015` | OA-15724 | 제한 없음 | 1회성데이터 | 기획조정실 재정기획관 재정담당관 |
| `BizsuggRequest` | OA-15718 | 제한 없음 | 1회성데이터 | 기획조정실 재정기획관 재정담당관 |
| `BizsuggRv` | OA-15715 | 제한 없음 | 수시 | 기획조정실 재정기획관 재정담당관 |
| `BizsuggReply` | OA-15717 | 제한 없음 | 수시 | 기획조정실 재정기획관 재정담당관 |
| `SuggEvaluation` | OA-15708 | 제한 없음 | 수시 | 기획조정실 재정기획관 재정담당관 |
| `Department` | OA-15716 | 제한 없음 | 수시 | 기획조정실 재정기획관 재정담당관 |
| `ChunmanFreeSuggestions` | OA-2563 | 공공누리 1유형 : 출처표시 (상업적 이용 및 변경 가능) | 비정기(자료변경시) | 홍보기획관 콘텐츠담당관 |
| `LawsystemIdeaImporvement` | OA-15748 | 공공누리 1유형 : 출처표시 (상업적 이용 및 변경 가능) | 1회성데이터 | 기획조정실 정책기획관 법무담당관 |
| `InfoMvotingList` | OA-13442 | 공공누리 1유형 : 출처표시 (상업적 이용 및 변경 가능) | 매일1회 | 디지털도시국 디지털정책과 |
| `seoulInstituteInfo2` | OA-22697 | 제한 없음 | 1회성데이터 | 홍보협력팀 |
| `dataContest` | OA-22583 | 제한 없음 | 1회성데이터 | 디지털도시국 데이터전략과 |
| `dataRegionContest` | OA-22582 | 제한 없음 | 1회성데이터 | 디지털도시국 데이터전략과 |

- 참여예산 계열은 "이용허락범위 제한 없음", 자유제안·법령제안·엠보팅은 공공누리 1유형(출처표시). 처음 안내서의 "서울 전부 1유형"은 틀림
- `seoulInstituteInfo2`는 데이터셋 "제한 없음"이지만 행마다 RIGHTS 문구 별도, CREATOR에 저자 실명
- 원본시스템: 참여예산 = yesan.seoul.go.kr(참여예산관리시스템), 자유제안 = idea.seoul.go.kr, 엠보팅 = mvoting.seoul.go.kr

## 3. 공식 필드 의미 (핵심만, 전체는 spec/*.json)

- 접수 `bizSuggAcceptInfo`: FIS_YEAR 년도, SUGG_NO 제안번호, BIZ_NM 사업명, **PARTI_FG 사업유형(시정:D, 지역:L, 협치:G)**, SUBCOMM_NM 분야, PRO_INTENT 제안취지, BIZ_CONTENT1~7 사업내용, BIZ_EFFECT 사업효과, BIZ_ETC 기타, GOVE_EFFECT 협치기대효과, PROC_OPINION 협의공론과정, `*_1`·`*_2` = 같은 항목의 이어지는 부분, LIKE_CNT 좋아요, **MASTER_NO 통폐합번호**
- 선정 `bizSuggSelectionInfo`: 위 항목 1~7 분할 + BIZ_BASE 사업근거, BIZ_PROCEDURE 추진절차, COST_DETAIL 산출내역, RV_DESC 구체화 조정내용, EMBODY_NM 통폐합여부, TRANS_FG 이관내용
- 집행 `civilBudRec`(= `bizSuggExecutionInfo`): SLCTN_YR 선정년도, PRP_NO 제안번호, FRMT_BIZ_NM 편성사업명, SLCTN_PJTCO 총회선정사업비, BGT_FRMT_YN 예산편성여부, BIZ_PRPL_STP 사업추진단계, EXPND_AMT 지출금액
- 자유제안: TITLE 제안제목, CONTENT "제안내용"(실제는 상세페이지 URL), VOTE_CNT 공감, VOTE_DIS_CNT 비공감, VISIOIN_TXT 정책분류, REPLY_YN 답변여부
- 법령제안 `LawsystemIdeaImporvement`: TITLE 과제/법령명, CONTROVERSIAL 현황및문제점, IMPROVEMENT 아이디어제안, INSTITUTION 관련법령, GOVERNMENT1~3 건의부처, PROGRESS 진행상황
- 엠보팅: VOTE_SJ 제목, VOTE_DC 투표취지, VOTE_SE 정책투표/우리끼리, **RFLRT 정책반영유무(유 805 / 무 8,568)**, RFLRT_EURL 상세 URL
- 공식 설명과 실데이터가 다른 곳
  - `civilBudRec` 상세설명·첨부파일명은 "접수정보, 제안취지·사업내용 포함"이라 돼 있으나 실제는 집행 12컬럼. 첨부 CSV(CP949, 6,405행)도 API와 동일
  - 법령제안 PROGRESS 공식 코드는 1~5인데 실제 1~10. 2012~2014는 4~10, 2015년 이후 1~3만 씀 → 의미 미확정
  - `BizsuggrvVote2014` 설명이 PART_MEMBER_CD/NM 서로 뒤바뀜(NM 칸에 실명)

## 4. 서비스별 결론

### A. 아이디어 본문 소스 (core.idea 후보)

| 서비스 | 건수 | 기간 | 행 키 | 본문 | 판정 |
|---|---|---|---|---|---|
| `bizSuggAcceptInfo` | 28,811 | 2013~2026 | FIS_YEAR+SUGG_NO | 섹션 합성 시 중앙값 452자, 90% 1,338자, 최대 10,303자, 총 1,932만 자 | **핵심 소스** |
| `LawsystemIdeaImporvement` | 613 | 2012~2022 | SEQ | 문제점+개선안 | 소스 추가(improvement_proposal) |
| `ChunmanFreeSuggestions` | 20,126 | 2017-10~ | SN | API엔 없음. 상세페이지에 [현황 및 문제점][개선방안][기대효과] 구조 본문 있음 | 제목만 적재 가능. 본문은 별도 수집 결정 필요 |
| `BizInter2015` | 7,193 | 2015~2016 | FIS_YEAR+SUGG_NO | 있음 | 접수와 6,579건 중복(6,177건 본문 동일). 나머지 614건 중 596건은 취소 → 실질 추가 18건. **별도 소스로 넣지 않음** |
| `InfoMvotingList` | 9,373 | 2014~2026 | VOTE_NO(5쌍 중복) | VOTE_DC 58.5%, HTML | 아이디어가 아니라 투표 안건. 정책투표 2,400건만 신호용 후보 |
| `seoulInstituteInfo2` | 93 | - | IDENTIFIER | DESCRIPTION 대부분 논문 목차 HTML | 가치 낮음, 저자 실명 → 제외 |

### B. 접수에 붙일 라벨·메타 (별도 idea 아님)

| 서비스 | 붙는 정보 | 조인 |
|---|---|---|
| `bizSuggSelectionInfo` 2,658 | 선정 여부, 다듬어진 사업명·본문, 통폐합·구체화, 사업근거·추진절차·산출내역 | 같은 키 2,529 + 통폐합 129건은 접수.MASTER_NO로(127 확인) → 접수 3,142행이 선정과 연결 |
| `civilBudRec` 6,405 | 편성여부·추진단계·지출 | 선정 키 2,658 전부 포함 |
| `BizsuggReply` 15,565 | 시민 댓글(평균 53자) | 99.9% 키 조인 |
| `SuggEvaluation` 3,436 | 평가 점수·순위 | FIS_YEAR+CHASU+SUGG_NO |
| `BizsuggRv` 11,811 | 부서 검토의견(BIZ_EVAL, 2013~2016) | FIS_YEAR+SUGG_NO+DEPT_CD. **REVIEW_ID·REVIEW_TEL_NO(검토자 ID·전화) 적재 금지** |
| `Department` 207 | SUBCOMM_CD → 분야명 | 연도별 코드표 |

### C. 제외

`BizMonitor`·`BizField`·`BizEval`(위원 의견·평가, 위원 코드/ID), `BizsuggrvVote2014`(위원 실명), `LawsystemImprovement`(3건, 제안자 실명), `BizsuggRequest`(149건, 번호체계 달라 조인 불가, 절반 취소), `seoulInstituteInfo10`(공공누리 4유형 변경금지), `dataContest`·`dataRegionContest`(기존 seed와 동일: 본선 70/70 일치, 예선은 seed 2,190 + 빈 행 1)

## 5. 라벨 쓸 때 함정 (AI 학습·평가용)

- **예산편성여부는 2020년 이후만 의미 있음.** 2012~2019는 전부 "미편성"인데 같은 행의 추진단계는 "완료"가 대부분(2013~2017). 미편성 = 실패로 쓰면 안 됨
- 추진단계도 2018년 이후 대부분 빈값
- 총회선정사업비는 2017년 이후만
- 좋아요(LIKE_CNT)는 2017년 이후만 0이 아님
- **탈락 단계 정보가 API에 없음.** 원본 사이트(yesan.seoul.go.kr)엔 단계코드 11 접수 / 12 분류(미선정) / 13 분류(선정) / 21 심사(미선정) / 22 심사(선정) / 31 투표(미선정) / 32 투표(선정) / 41 예산(미편성) / 42 예산(편성)과 주제코드가 있으나, robots.txt가 `/join/`(제안사업 검색)을 막음 → 자동 수집 불가. 필요하면 제공부서(재정담당관)에 API 항목 추가 요청
- 같은 제안이 해마다 재접수됨: 정규화 제목 같은 묶음 1,114개(5,223행, 그중 818개는 연도 걸침), 본문까지 동일 315묶음(654행, 217개 연도 걸침). 중복 제거하지 말고 "재제안" 관계로 남기는 게 유사도 분석에 유리

## 6. 정제 규칙 (적재 전 필수)

1. 분할 필드는 순서대로 그대로 이어 붙임(구분자 금지, 문장 중간 절단 확인). `BIZ_CONTENT1..7`은 정확히 1,000자 단위, `PRO_INTENT→_1→_2` 등은 1,000자 단위 아님
2. 섹션 라벨 유지: `[제안취지] [사업내용] [사업효과] [기타] [협치기대효과] [협의공론과정]` → P1 카드(problem/solution 추출)에 유리
3. HTML 엔티티 해제(접수 78행, 자유제안 제목 202행, 엠보팅 1,632행은 태그까지 제거)
4. 줄바꿈 `\r\n`, `\r\r\n`(법령제안) → `\n`
5. 개인정보: 접수 본문 휴대폰 형태 51건·이메일 20건·"제안자 OOO" 형태 75건, BizInter2015 이메일 11건 → 기존 ingest 원칙대로 적재 때 마스킹
6. 중복: civilBudRec 완전중복 1행, 엠보팅 VOTE_NO 5쌍

## 7. core.idea 매핑안 (기존 AWARD_RECORD_COLUMNS 기준, 구현 전)

| 컬럼 | 시민참여예산 접수 | 법령제도개선 제안 | 상상대로 자유제안 |
|---|---|---|---|
| 원천키 → idea_id | `FIS_YEAR+SUGG_NO` | `SEQ` | `SN` |
| title | BIZ_NM(엔티티 해제) | TITLE | TITLE(엔티티 해제) |
| body | 6장 규칙으로 합성 | [현황및문제점]+[아이디어제안] | 없음(본문 수집 시 채움) |
| year | FIS_YEAR | RDATE 연도 | REG_DATE 연도 |
| award | 선정/통폐합선정/null(선정 조인) | null | null |
| category | 분야(연도별 이름 정규화) | INSTITUTION | VISIOIN_TXT |
| host_org / contest | 서울특별시 / 시민참여예산 {연도} | 서울특별시 / 법령제도개선 제안 | 서울특별시 / 상상대로 서울 |
| source_url | 데이터셋 페이지(개별 URL 없음, 원본 사이트 robots 차단) | 데이터셋 페이지 | CONTENT의 공식 상세 URL |
| extra | record_kind=public_proposal, 사업유형, 위치, 소요사업비, 좋아요, MASTER_NO, 선정·집행·댓글 요약 | record_kind=improvement_proposal, 진행상황, 건의부처 | record_kind=public_proposal, 공감·비공감·답변여부 |

- 기존 `mapped_contest_csv`는 본문 컬럼을 `\n`으로 이어 붙여서 1,000자 분할 필드에 쓰면 문장이 깨짐 → JSONL 전용 어댑터 또는 사전 병합 CSV가 필요
- 반출(export_grade)·공개(public_ok)는 라이선스상 가능해 보이나 정책 승인은 사람이 결정

## 8. 남은 결정

- 자유제안 본문 20,126건 수집 여부(robots는 허용, 상세에 작성자 마스킹명 "김 * *" 있음 → 저장 제외 필요)
- 탈락 단계 라벨을 재정담당관에 요청할지
- 엠보팅 정책투표를 신호(바뀐 것)로 쓸지
