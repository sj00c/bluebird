# 데이터 출처 명세

생성 2026-10-12 — `bluebird export provenance` 가 DB와 레지스트리에서 만든다. 손으로 고치지 말고 다시 생성한다.

아이디어 **66,067건**, 소스 66개. 모두 공식 공개 경로(공공데이터포털 파일/API, 기관 공개 게시물, KIPRIS Plus 벌크)에서 받았다. 스크래핑 없음.

## 한눈에

| 구분 | 건수 |
|---|---:|
| 기록 종류: 수상작 | 36,181 |
| 기록 종류: 국민·주민 제안 | 22,464 |
| 기록 종류: 출품작 | 7,199 |
| 기록 종류: 직원 개선제안 | 223 |
| 대회 대상자: student | 35,589 |
| 대회 대상자: unknown | 30,478 |

제외 후보 이유(걸러내지 않음, 받는 쪽이 고른다):

| 이유 | 뜻 | 건수 |
|---|---|---:|
| `student_contest` | 초·중·고 학생 대회 | 35,589 |
| `public_proposal` | 참여예산·국민/주민 제안 | 22,464 |
| `duplicate_title` | 같은 제목이 이미 있음 | 2,574 |
| `certified_product` | 상품화 뒤 받는 인증 | 2,415 |
| `improvement_proposal` | 직원 개선제안 | 223 |
| `internal_activity` | 기관 내부 활동 사례 | 112 |
| `teaching_case` | 수업·교육 사례 | 6 |

## 외부 공유 보류 소스

라이선스에 '보류'가 박힌 소스. xlsx 내보내기 기본값에서 빠지고 `--include-held` 로만 들어간다.

| 소스 | 건수 | 라이선스 |
|---|---:|---|
| KIPRIS Plus 공모전 아이디어 벌크(1979~2014) | 26,434 | KIPRIS Plus 이용약관 — 공개·외부 전송은 약관 확인 전까지 보류(data.go.kr 15006010 표기 '제한 없음'과 충돌, 10/26 게이트) |
| 국립중앙과학관 전국학생과학발명품경진대회 공개 출품작 목록(2015~2026 검색 범위) | 3,300 | 국립중앙과학관 공개 게시물 — 이용조건 검토 전 공개·외부전송 보류 |
| 국립중앙과학관 전국과학전람회 공개 출품작 목록(2015~2026 검색 범위) | 3,267 | 국립중앙과학관 공개 게시물 — 이용조건 검토 전 공개·외부전송 보류 |
| 한국디자인진흥원 우수디자인(GD)상품선정 공개 수상작 | 2,415 | KIDP All Rights Reserved — 이용조건 검토 전 공개·외부전송 보류 |
| 범정부 공공데이터 활용 창업경진대회 예선기관 수상작(2013~2024) | 2,190 | 공공데이터포털 개방 데이터 (이용조건 재확인 필요) |
| 한국디자인진흥원 청소년디자인전람회 공개 수상작 | 1,916 | KIDP All Rights Reserved — 이용조건 검토 전 공개·외부전송 보류 |
| 한국디자인진흥원 대한민국디자인전람회 공개 수상작 | 1,257 | KIDP All Rights Reserved — 이용조건 검토 전 공개·외부전송 보류 |

## 소스별 상세

| 소스 id | 이름 | 기록 종류 | 건수 | 연도 | 본문 | 처음 받은 날 | 마지막 | 출처 | 라이선스 | 어떻게 |
|---|---|---|---:|---|---:|---|---|---|---|---|
| `kipris_contest_idea_bulk` | KIPRIS Plus 공모전 아이디어 벌크(1979~2014) | 수상작 | 26,434 | 1979~2014 | 26,434 | 2026-10-07 | 2026-10-07 | https://plus.kipris.or.kr | KIPRIS Plus 이용약관 — 공개·외부 전송은 약관 확인 전까지 보류(data.go.kr 15006010 표기 '제한 없음'과 충돌, 10/26 게이트) | `sources.toml` · 파일 `kipris_idea_master.csv` · 어댑터 `kipris_idea_master` |
| `daegu_budget_project_proposals` | 대구광역시_주민참여예산 시민 제안사업 구체화 정보 | 국민·주민 제안 | 7,159 | 2016~2025 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15133517/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15133517 |
| `gwangju_budget_proposals` | 전남광주통합특별시_시민광장 광주온 시민참여예산 제안사업 정보 | 국민·주민 제안 | 5,986 | 2015~2024 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15132901/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15132901 |
| `science_invention_archive_2015_onward` | 국립중앙과학관 전국학생과학발명품경진대회 공개 출품작 목록(2015~2026 검색 범위) | 출품작 | 3,300 | 2015~2026 | 0 | 2026-10-08 | 2026-10-08 | https://www.science.go.kr/mps/1075/bbs/424/moveBbsNttList.do | 국립중앙과학관 공개 게시물 — 이용조건 검토 전 공개·외부전송 보류 | `science-contest-sources.toml` · 수집기 `science_archive` |
| `science_exhibition_archive_2015_onward` | 국립중앙과학관 전국과학전람회 공개 출품작 목록(2015~2026 검색 범위) | 출품작 | 3,267 | 2015~2025 | 0 | 2026-10-08 | 2026-10-08 | https://www.science.go.kr/mps/1079/bbs/423/moveBbsNttList.do | 국립중앙과학관 공개 게시물 — 이용조건 검토 전 공개·외부전송 보류 | `science-contest-sources.toml` · 수집기 `science_archive` |
| `ulsan_budget_proposals` | 울산광역시_주민참여예산 제안 사업 목록 데이터 | 국민·주민 제안 | 2,946 | 2021~2026 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15164278/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15164278 |
| `kidp_good_design_projects` | 한국디자인진흥원 우수디자인(GD)상품선정 공개 수상작 | 수상작 | 2,415 | 2019~2025 | 0 | 2026-10-08 | 2026-10-08 | https://award.kidp.or.kr/Exhibit/winners.do?cd_gubun=1 | KIDP All Rights Reserved — 이용조건 검토 전 공개·외부전송 보류 | `design-contest-sources.toml` · 수집기 `kidp_awards` |
| `gov_startup_prelim_awards` | 범정부 공공데이터 활용 창업경진대회 예선기관 수상작(2013~2024) | 수상작 | 2,190 | 2012~2024 | 252 | 2026-10-07 | 2026-10-07 | https://www.data.go.kr/data/15146089/fileData.do | 공공데이터포털 개방 데이터 (이용조건 재확인 필요) | `sources.toml` · 파일 `awards_master_2013_2024.csv` · 어댑터 `awards_csv` |
| `kidp_youth_design_projects` | 한국디자인진흥원 청소년디자인전람회 공개 수상작 | 수상작 | 1,916 | 2019~2025 | 0 | 2026-10-08 | 2026-10-08 | https://award.kidp.or.kr/Exhibit/winners.do?cd_gubun=3 | KIDP All Rights Reserved — 이용조건 검토 전 공개·외부전송 보류 | `design-contest-sources.toml` · 수집기 `kidp_awards` |
| `daegu_budget_selected_projects` | 대구광역시_주민참여예산 시민 선정사업 상세정보 | 국민·주민 제안 | 1,472 | 2015~2024 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15133520/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15133520 |
| `kidp_korea_design_projects` | 한국디자인진흥원 대한민국디자인전람회 공개 수상작 | 수상작 | 1,257 | 2019~2025 | 0 | 2026-10-08 | 2026-10-08 | https://award.kidp.or.kr/Exhibit/winners.do?cd_gubun=2 | KIDP All Rights Reserved — 이용조건 검토 전 공개·외부전송 보류 | `design-contest-sources.toml` · 수집기 `kidp_awards` |
| `geoje_budget_proposals` | 경상남도 거제시_주민참여예산현황 | 국민·주민 제안 | 1,196 | 2017~2025 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15145448/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15145448 |
| `science_museum_awards` | 국립중앙과학관 수상작(전국과학전람회 제69회·학생과학발명품경진대회 제44회) | 수상작 | 970 | 2022~2023 | 0 | 2026-10-07 | 2026-10-07 | https://www.data.go.kr/data/15135618/fileData.do | 이용허락범위 제한 없음 | `sources.toml` · 파일 `national_science_museum_awards_20240909.csv` · 어댑터 `science_museum_csv` |
| `incheon_port_public_proposals` | 인천항만공사_홈페이지 국민의견수렴 정보 | 국민·주민 제안 | 602 | 2019~2025 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15148814/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15148814 |
| `yuseong_budget_proposals` | 대전광역시 유성구_홈페이지구민사업제안 | 국민·주민 제안 | 554 | 2026~2026 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15160908/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15160908 |
| `kaia_contest_submissions` | 국토교통과학기술진흥원_공모전 신청현황 | 출품작 | 503 | 2020~2023 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15162866/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15162866 |
| `jeju_budget_proposals` | 제주특별자치도_주민참여예산신청현황 | 국민·주민 제안 | 440 | 2025~2025 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15071627/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15071627 |
| `sejong_budget_proposals` | 세종특별자치시_주민제안사업 | 국민·주민 제안 | 421 | 2025~2025 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15160880/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15160880 |
| `gwangjin_budget_proposals` | 서울특별시 광진구_주민참여예산 현황 | 국민·주민 제안 | 219 | 2016~2026 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15034406/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15034406 |
| `chungbuk_budget_proposals` | 충청북도_주민참여예산 세부내역 | 국민·주민 제안 | 218 | 2026~2026 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15161856/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15161856 |
| `nonsan_district_budget_proposals` | 충청남도 논산시_주민참여예산사업(읍면동) | 국민·주민 제안 | 186 | 2026~2026 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15145205/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15145205 |
| `gyeongnam_budget_proposals` | 경상남도_주민참여예산 현황 | 국민·주민 제안 | 164 | 2024~2026 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15162158/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15162158 |
| `happy_rural_community_awards` | 한국농어촌공사_행복농촌만들기 콘테스트 수상 정보 | 수상작 | 161 | 2015~2022 | 161 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15140150/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15140150 |
| `jeonnam_awarded_proposals` | 전남광주통합특별시_우수제안 목록 정보 | 수상작 | 159 | — | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15105816/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15105816 |
| `yeongdeungpo_budget_proposals` | 서울특별시_영등포구_주민참여예산현황 | 국민·주민 제안 | 144 | 2017~2026 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15048758/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15048758 |
| `yangpyeong_budget_proposals` | 경기도 양평군_주민참여예산 최종사업 선정목록 | 국민·주민 제안 | 111 | — | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15139350/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15139350 |
| `rural_sixth_industry_awards` | 농림수산식품교육문화정보원_6차산업 경진대회수상사례 | 수상작 | 109 | — | 109 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15124203/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15124203 |
| `khnp_quality_circle_awards` | 한국수력원자력(주)_전국 품질분임조 수상내역 | 수상작 | 100 | 2011~2025 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15087097/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15087097 |
| `mafra_agrifood_contest` | 농림축산식품부 농식품 공공·빅데이터 활용 창업경진대회(2015~2023) | 수상작 | 92 | 2015~2023 | 0 | 2026-10-07 | 2026-10-07 | https://www.data.go.kr/data/15131197/fileData.do | 이용허락범위 제한 없음 | `sources.toml` · 파일 `mafra_agrifood_bigdata_contest_info.csv` · 어댑터 `mafra_contest_csv` |
| `daegu_seogu_budget_proposals` | 대구광역시 서구_주민참여예산사업 현황 | 국민·주민 제안 | 88 | — | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15092743/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15092743 |
| `sejong_education_public_proposals` | 세종특별자치시교육청_제안사업공모정보 | 국민·주민 제안 | 86 | 2022~2022 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15150602/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15150602 |
| `ulsan_open_data_contest_entries` | 울산광역시_공공데이터 활용 창업경진대회 | 출품작 | 80 | 2023~2025 | 70 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15153117/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15153117 |
| `kf_public_diplomacy_projects` | 한국국제교류재단_국민공공외교프로젝트목록 | 국민·주민 제안 | 79 | 2019~2024 | 79 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15147096/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15147096 |
| `daejeon_transit_power_proposals` | 대전교통공사_전력기술팀 제안(창안) 과제 제출 현황 | 직원 개선제안 | 76 | 2006~2025 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15098477/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15098477 |
| `public_design_ideas` | 공공디자인 국민아이디어공모 수상작 | 수상작 | 72 | 2020~2023 | 71 | 2026-10-07 | 2026-10-07 | https://www.data.go.kr/data/15138745/fileData.do | 이용허락범위 제한 없음 | `sources.toml` · 파일 `public_design_idea_15138745.csv` · 어댑터 `design_idea_csv` |
| `gov_startup_final_awards` | 범정부 공공데이터 활용 창업경진대회 본선 수상작(2019~2025) | 수상작 | 70 | 2019~2025 | 69 | 2026-10-07 | 2026-10-07 | https://www.data.go.kr/data/15146087/fileData.do | 공공누리 제1유형(출처표시) | `sources.toml` · 파일 `gov_opendata_startup_contest_final_awards_2019_2025.xlsx` · 어댑터 `startup_final_xlsx` |
| `daejeon_transit_control_proposals` | 대전교통공사_제어기술팀 제안(창안)과제 제출현황 | 직원 개선제안 | 64 | 2006~2026 | 64 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15043816/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15043816 |
| `busan_budget_proposals` | 부산광역시_주민참여예산 예산편성 목록 | 국민·주민 제안 | 64 | — | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15161622/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15161622 |
| `korea_public_design_awards` | 한국공예디자인문화진흥원_공공디자인대상 수상작 정보 | 수상작 | 61 | 2020~2023 | 61 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15087221/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15087221 |
| `seodaemun_budget_proposals` | 서울특별시 서대문구_주민참여예산 승인사업  현황 | 국민·주민 제안 | 51 | 2021~2021 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15048767/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15048767 |
| `gyeongbuk_budget_proposals` | 경상북도_주민참여예산신청현황 | 국민·주민 제안 | 49 | 2026~2026 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15160654/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15160654 |
| `yeonggwang_contest_proposals` | 전남광주통합특별시 영광군_대표홈페이지_제안공모전 | 출품작 | 49 | — | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15153466/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15153466 |
| `kogas_technology_research_proposals` | (주)한국가스기술공사_연구관리시스템_제안 | 직원 개선제안 | 46 | 2013~2019 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15146845/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15146845 |
| `family_support_public_proposals` | 한국건강가정진흥원_누리집 국민제안정보 | 국민·주민 제안 | 36 | 2017~2024 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15153784/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15153784 |
| `jeonnam_citizen_proposals` | 전남광주통합특별시_소통인전남 제안광장 | 국민·주민 제안 | 36 | 2023~2024 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15130550/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15130550 |
| `goyang_budget_proposals` | 경기도 고양시_주민참여예산 반영사업 | 국민·주민 제안 | 33 | — | 33 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15127194/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15127194 |
| `namdong_budget_proposals` | 인천광역시 남동구_주민참여예산사업 반영결과 | 국민·주민 제안 | 30 | 2023~2023 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15087648/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15087648 |
| `ai_education_teacher_projects` | 한국과학창의재단_인공지능(AI)교육 교사연구회 성과물 목록 | 직원 개선제안 | 30 | 2020~2020 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15091274/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15091274 |
| `daegu_youth_budget_awards` | 대구광역시_주민참여예산 청소년우수사업 정보 | 수상작 | 30 | 2022~2025 | 30 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15136149/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15136149 |
| `senior_employment_idea_awards` | 한국노인인력개발원_인천지역 신규 노인일자리 개발을 위한 아이디어 공모전 | 수상작 | 28 | — | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15156525/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15156525 |
| `jeonbuk_budget_proposals` | 전북특별자치도_주민참여예산신청현황 | 국민·주민 제안 | 25 | 2024~2026 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15160678/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15160678 |
| `kamco_data_contest_awards` | 한국자산관리공사_연도별 데이터 분야 공모전 수상작 정보 | 수상작 | 25 | 2021~2025 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15156683/fileData.do | 공공저작물 : 출처표시, 상업적 이용금지, 변경금지 (제 4유형) | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15156683 |
| `yeonsu_budget_proposals` | 인천광역시 연수구_주민참여예산 운영현황 | 국민·주민 제안 | 22 | — | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15087402/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15087402 |
| `youth_data_contest_awards` | 성평등가족부_경진대회 수상 정보 | 수상작 | 22 | 2023~2026 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15166904/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15166904 |
| `nonsan_department_budget_proposals` | 충청남도 논산시_주민참여예산사업(사업부서) | 국민·주민 제안 | 21 | 2025~2025 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15145203/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15145203 |
| `fire_industry_technology_awards` | 한국소방산업기술원_소방산업대상 공모전 수상작 목록 | 수상작 | 19 | 2025~2025 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15132795/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15132795 |
| `gangwon_budget_proposals` | 강원특별자치도_주민참여예산 제안사업 현황 | 국민·주민 제안 | 17 | 2025~2026 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15162578/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15162578 |
| `busan_urban_innovation_awards` | 부산도시공사_경영혁신 적극행정 우수사례 목록 | 수상작 | 12 | — | 12 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15155587/fileData.do | 공공저작물 : 출처표시 (제 1유형) | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15155587 |
| `serious_game_awards` | 한국콘텐츠진흥원_기능성게임 수상작 정보 | 수상작 | 12 | 2020~2023 | 11 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15150108/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15150108 |
| `namdong_citizen_proposals` | 인천광역시 남동구_남동구홈페이지_구민제안 | 국민·주민 제안 | 9 | 2020~2021 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15155076/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15155076 |
| `gwangju_open_data_contest_awards` | 전남광주통합특별시_광주 공공데이터 활용 경진대회 수상현황 | 수상작 | 9 | 2026~2026 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15074003/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15074003 |
| `daejeon_junggu_policy_awards` | 대전광역시 중구_정책제안 공모전 시상 결과 | 수상작 | 7 | 2024~2024 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15139894/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15139894 |
| `software_teaching_case_awards` | 한국과학창의재단_소프트웨어(SW) 수업 우수사례 공모전 수상작 목록 | 수상작 | 6 | 2020~2020 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15091356/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15091356 |
| `kps_employee_ideas` | 한전케이피에스주식회사_아이디어 | 직원 개선제안 | 5 | — | 5 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15137044/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15137044 |
| `fire_industry_design_awards` | 한국소방산업기술원 소방산업 우수 디자인 공모전 수상작 목록 | 수상작 | 5 | 2025~2025 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15039590/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15039590 |
| `incheon_facilities_public_ideas` | 인천시설공단_공단 홈페이지 아이디어 뱅크 | 직원 개선제안 | 2 | 2009~2009 | 0 | 2026-10-08 | 2026-10-08 | https://www.data.go.kr/data/15138358/fileData.do | 이용허락범위 제한 없음 | `contest-sources.toml` · 수집기 `data_go_csv` · 데이터셋 15138358 |

## 받지 않은 것 (조사만)

- KIPRIS Plus 아이디어 DB API 38,563건: 1965~2014 학생 대회 98%, 벌크와 84% 중복 → 미적재. `docs/API_KEYS.md`
- 서울 열린데이터 5종(참여예산 28,811 등)·경기 참여예산 4,138·권익위 공개제안(연 1.2~1.8만): 키 확인 완료, 적재는 결정 대기. `docs/API_KEYS.md`
- 공공데이터포털 전체 카탈로그 8,142행 스캔 결과와 143개 후보: `docs/SOURCES.md`
- 성인 창업 공모(K-스타트업 왕중왕전·관광벤처 등)는 데이터셋이 없고 기관 페이지 표·보도자료만: `docs/REVIVAL_SOURCES.md`
