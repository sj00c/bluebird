# 공모전 데이터 API 키 신청 체크리스트

조사 근거: autoresearch `contest-api-survey`(2026-10-08) + `contest-api-survey-regional`(2026-10-09).
받은 키는 `.env`에만 넣는다(git 제외). 코드 wiring은 키 도착 후 별도 작업 — 현재 코드가 읽는 변수는 `DATA_GO_KR_KEY`·`KIPRIS_PLUS_KEY`·`BIZINFO_KEY` 셋이고, `SEOUL_OPENAPI_KEY`·`GG_OPENAPI_KEY`는 아직 아무 코드도 읽지 않는다.

키 검증은 `set -a; . .env; set +a` 후 아래 curl.

---

## A. 포털 가입 + 인증키 (즉시 발급)

### 1. 서울 열린데이터광장 → `SEOUL_OPENAPI_KEY`
- 신청: https://data.seoul.go.kr/together/guide/useGuide.do → 회원가입 → **일반 인증키 신청** (지하철 키 아님)
- 활용용도 예시: "공공기관 공모전 아이디어 중복·유사도 분석"
- 조건: 1회 최대 1,000건, 일 한도 없음(활용사례 갤러리 등록 시 제약 해제), 공공누리 1유형
- 키 1개로 5종 전부:

| 서비스 | 내용 | 건수 | 수준 |
|---|---|---|---|
| `bizSuggAcceptInfo` | 시민참여예산사업 접수정보 (OA-15412) | 28,811 | **제안 본문** |
| `bizSuggSelectionInfo` | 시민참여예산사업 선정정보 (OA-15414) | 2,658 | 본문(선정분) |
| `ChunmanFreeSuggestions` | 상상대로 서울 자유제안 (OA-2563) | 20,116 | 제목+메타(본문은 URL) |
| `dataContest` | 범정부 창업경진 본선 수상작 (OA-22583) | 70 | 기존 적재 15146087 갱신용 |
| `dataRegionContest` | 범정부 창업경진 예선기관 수상작 (OA-22582) | 2,191 | 기존 적재 15146089 갱신용 |

- 검증: `curl "http://openapi.seoul.go.kr:8088/$SEOUL_OPENAPI_KEY/json/bizSuggAcceptInfo/1/5/"` → `list_total_count: 28811`
- 패턴: `http://openapi.seoul.go.kr:8088/{KEY}/json/{SERVICE}/{start}/{end}/[{FIS_YEAR}]`

### 2. 경기데이터드림 → `GG_OPENAPI_KEY`
- 신청: https://data.gg.go.kr/portal/openapi/introPage.do → 회원가입 → OpenAPI > **인증키 발급** (로그인 필요)
- 대상: `tbggrpbudgresdntprpbizl` 주민참여예산 주민제안사업 목록 4,138건(2020~2025) — 제목·제안구분·사업비·**선정여부·편성사업명**, 본문 없음
- 조건: 연간 갱신, 상업적이용허용·콘텐츠변경불가
- 검증: `curl -A "Mozilla/5.0" "https://openapi.gg.go.kr/tbggrpbudgresdntprpbizl?KEY=$GG_OPENAPI_KEY&Type=json&pIndex=1&pSize=2"` → `list_total_count: 4138` **(2026-10-12 확인)**
- 주의: **curl 기본 User-Agent는 WAF가 차단**("보안 정책에 의해 차단", euc-kr HTML 반환). 브라우저 UA 헤더 필수 — wiring 시 egress에 UA 지정
- 참고: KEY 생략 시 샘플 모드로도 전체 total 반환됨

---

## B. data.go.kr 활용신청 → `DATA_GO_KR_KEY` (기존 변수, 키 1개 공용)

이미 data.go.kr 계정·키가 있으면 각 페이지에서 **[활용신청]**만 누르면 된다. 전부 개발단계 자동승인; 공공기관은 운영계정 전환도 자동.

| # | 데이터 | 신청 페이지 | 수준 | 한도 | 비고 |
|---|---|---|---|---|---|
| 3 | 권익위 **공개제안조회서비스** 15059423 | https://www.data.go.kr/data/15059423/openapi.do | **제안 본문** | 개발 10,000/일 | 최우선. 스웨거 미등록 → 참고문서 docx 기준으로 파라미터 확정 필요 |
| 4 | 권익위 공모제안조회서비스 15059115 | https://www.data.go.kr/data/15059115/openapi.do | 공모 안건 | 10,000/일 | `sources_check.py` 코드 있음 |
| 5 | 창업진흥원 K-Startup 사업공고 15125364 | https://www.data.go.kr/data/15125364/openapi.do | 공고 | 10,000/일 | `announce.py` 코드 있음 |
| 6 | 중기부 중소기업지원사업 공고 15113297 | https://www.data.go.kr/data/15113297/openapi.do | 공고 | **개발 100/일** | 운영계정 전환 권장 |
| 7 | 대구북구 주민참여예산 선정결과 15095930 | https://www.data.go.kr/data/15095930/openapi.do | 제목만 | 10,000/일 | 선택 |

- 검증(15059115): `curl -G "https://apis.data.go.kr/1140100/PublicProposalService2/PublicProposalItem" --data-urlencode "serviceKey=$DATA_GO_KR_KEY" -d assProNo=1` → `resultCode S00` **(2026-10-12 확인)**. `assProNo` 없이 호출하면 `HTTP_ERROR 04`
- 검증(15125364): `curl -G "https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01" --data-urlencode "serviceKey=$DATA_GO_KR_KEY" -d page=1 -d perPage=1 -d returnType=json` **(확인)**
- 검증(15113297): `curl -G "https://apis.data.go.kr/1421000/mssBizService_v2/getbizList_v2" --data-urlencode "serviceKey=$DATA_GO_KR_KEY" -d pageNo=1 -d numOfRows=1` → totalCount 2,214 **(확인)**
- **15059423 공개제안 — 참고문서 docx로 스펙 확정 (2026-10-12 확인)**
  - 목록 `http://apis.data.go.kr/1140100/OpenProposalService2/OpenProposalList?serviceKey&firstIndex=1&recordCountPerPage=100[&regFrom=YYYYMMDD&regTo=YYYYMMDD&keyword&searchType=title|ancName&statusCode]` — **regFrom~regTo 1년 초과 시 `HTTP_ERROR 04`**(연 단위로 끊어서 스윕). 연간 건수: 2020년 12,031 / 2025년 17,915 / 2026년(10월) 18,503
  - 항목 `OpenProposalService2/OpenProposalItem?serviceKey&petiNo=` → `title`·`content`·`summary`·`improveIdea`·`effect`·`ancName`·`regDate`·`recomCnt`·`answerList[]`
  - **`peterName`(신청인명)이 실제로 채워져 옴 → 적재 시 반드시 drop.** `fileList[].orglFileNm`도 개인정보 가능성 있어 보류
  - 응답은 JSON(`resultCode S00`), 게이트웨이 SSL 미지원이라 http
- 주의: `serviceKey`는 **Decoding 키**를 `--data-urlencode`로 넣는다. Encoding 키를 그대로 붙이면 이중 인코딩으로 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`

---

## C. 기관 자체 키

### 8–9. KIPRIS Plus → `KIPRIS_PLUS_KEY` (기존 변수)
- **2026-10-12 이용신청 완료, 호출 확인.** 신청 경로: 로그인 → 데이터 신청 > Open API https://plus.kipris.or.kr/portal/data/request/apiFsmtmList.do?menuNo=290005 → 아이디어DB 선택 → 장바구니. 상품 페이지 http://plus.kipris.or.kr/portal/data/util/DBII_000000000000228/view.do?menuNo=210007&subTab=SC002
- 조건: 월 1,000회 무료(수수료 페이지 기준 공공기관은 초과분 50% 할인, 기본 무료 아님). 무료 확대는 데이터 기프트 제도 https://plus.kipris.or.kr/portal/bbs/list.do?bbsId=B0000007&menuNo=200023
- **실측 스펙** (페이지 문서와 다름):
  - `openingDate=YYYYMMDD` 단일 날짜만 동작. `~`·`-`·`,` 구간 표기는 전부 `totalCount 0` → 날짜 스윕 불가
  - **`ideaName=%` 가 와일드카드로 전체 38,563건 매칭**. 페이지네이션은 `docsStart`(1부터)·`docsCount`(**최대 100**) → 전수 386회 호출
  - 출력 16필드: `ideaName`·`ideaContent`(100%, 중앙값 437자)·`awardInformation`·`contestName`·`contestYear`·`hostInstitution`·`managementInstitution`·`ipcCode`·`domesticDesignClassification`·`locarnoClassification`·`technologyClassification`·`openingDate`(52%)·`openingMethod`·`originalLink`(100%, science.go.kr/ssp.re.kr 상세 URL = 벌크 `source_url`과 조인 키)·`drawingPath`·`interfaceApplicationNumber`(2%). **수상자 이름 필드 없음**(벌크와 달리 PII 없음)
- **벌크 대비 실제 추가분 (7.2% 층화 표본 2,763건 추정)**:
  - 연도 범위 **1965~2014(+2015 소수)** — 2015 이후 데이터 없음. "증분" 용도는 성립 안 함
  - 벌크에 없는 것: ① 1965~1978 전국과학전람회 초기 ≈4,000건 ② 시·도 예선(서울특별시학생탐구발표대회·서울특별시학생과학발명품경진대회·대전/부산/강원 과학전람회 등) 1979~2014 ≈6,200건. 나머지 84%는 벌크와 같은 대회·연도(`originalLink`로 중복 제거)
  - 검증: `curl -A "Mozilla/5.0" "http://plus.kipris.or.kr/openapi/rest/IdeaDBInfoService/ideaDBInfo?ideaName=%25&docsCount=100&docsStart=1&accessKey=$KIPRIS_PLUS_KEY"` → `<totalCount>38563</totalCount>`
- 라이선스: KIPRIS Plus 약관 — 공개·외부 전송은 10/26 게이트 전까지 보류 (`sources.toml` kipris_contest_idea_bulk 참고)

### 10. 건설CALS (선택) → `CALS_OPENAPI_KEY`
- 신청: https://www.calspia.go.kr/io/openapi/gid/selectOpenApiIsRqsView.do
- 대상: 설계VE 상세 VE제안목록 `selectIoPtVEProposalList.do` — `ptlCmno`(공사관리번호) 필수라 공사별 조회만, 건설 전용
- 범위 경계. 필요 없으면 건너뜀

### 11. 기업마당 (선택) → `BIZINFO_KEY` (기존 변수)
- 신청: https://www.bizinfo.go.kr/ 로그인 → 마이페이지 → OpenAPI 인증키
- 6번(중기부 15113297)과 동일 원천. 둘 중 하나만
- 검증: `curl "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do?crtfcKey=$BIZINFO_KEY&dataType=json&searchCnt=1"`

---

## 키 없이 되는 것 (신청 불필요)

| 소스 | 엔드포인트 | 건수 |
|---|---|---|
| 충남넷 공모전 공지 | `https://www.chungnam.go.kr/cnbbs/openApiContestNoticeList.do?numOfRows=50&pageNo=1` | 107 (공고 본문 포함) |
| 충남넷 공모일정 | `https://www.chungnam.go.kr/cnbbs/openApiMainFxList.do?numOfRows=50&pageNo=1` | 56 |

## 신청해도 안 되는 것

- 민간 공모 포털 8개(위비티·씽굿·링커리어·콘테스트코리아·올콘·캠퍼스픽·데이콘·온오프믹스): 공식 API 없음
- 국민생각함·국민참여예산(mybudget)·내생각엔: 전용 API 없음
- 부산·전북·경북·광주온·인천 참여예산: 파일/LINK 전용(data.go.kr 파일데이터와 동일)

---

## `.env` 추가분 요약

```
# 서울 열린데이터광장 일반 인증키 (5종 공용)  https://data.seoul.go.kr
SEOUL_OPENAPI_KEY=
# 경기데이터드림 OpenAPI 인증키  https://data.gg.go.kr
GG_OPENAPI_KEY=
# 건설CALS (선택)  https://www.calspia.go.kr
CALS_OPENAPI_KEY=
```

기존 `DATA_GO_KR_KEY`·`KIPRIS_PLUS_KEY`·`BIZINFO_KEY`는 그대로 채운다. 네 개 다 들어오면 다음 단계는 레지스트리 wiring(서울 5종·경기 1종·권익위 공개제안·KIPRIS ideaDBInfo 증분) — 승인 후 시작.
