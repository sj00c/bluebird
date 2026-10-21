"""대회·제도 분류 규칙: 행 → (종류, 분야, 대회·제도). master.kind·field·program = refine이 이 규칙으로 채움.

- 종류 = 레지스트리 record_kind(공모전·시민 제안·직원 제안)
- 분야·대회·제도 = PROGRAM(소스 단위). BY_CONTEST 소스 = 원본 행 대회명(회차·연도·공백 제거)으로 나눔, 비면 PROGRAM 이름
- 매핑 없는 소스 = 분야 '미분류', 이름 = 소스 id
"""

from __future__ import annotations

import re

KIND = {"contest_award": "공모전", "contest_submission": "공모전", "public_proposal": "시민 제안",
        "improvement_proposal": "직원 제안"}
PROGRAM: dict[str, tuple[str, str]] = {
    "kipris_idea_api": ("과학·발명", "KIPRIS 아이디어DB(대회명 없음)"),
    "science_exhibition_archive_2015_onward": ("과학·발명", "전국과학전람회"),
    "science_invention_archive_2015_onward": ("과학·발명", "전국학생과학발명품경진대회"),
    "science_museum_awards": ("과학·발명", "국립중앙과학관 수상작(대회명 없음)"),
    "kidp_good_design_projects": ("디자인", "우수디자인(GD) 상품선정"),
    "kidp_korea_design_projects": ("디자인", "대한민국디자인전람회"),
    "kidp_youth_design_projects": ("디자인", "대한민국청소년디자인전람회"),
    "korea_public_design_awards": ("디자인", "대한민국 공공디자인대상"),
    "public_design_ideas": ("디자인", "공공디자인 국민아이디어공모"),
    "fire_industry_design_awards": ("디자인", "소방산업 우수 디자인 공모전"),
    "gov_startup_prelim_awards": ("공공데이터·창업", "범정부 공공데이터 활용 창업경진대회"),
    "gov_startup_final_awards": ("공공데이터·창업", "범정부 공공데이터 활용 창업경진대회"),
    "mafra_agrifood_contest": ("공공데이터·창업", "농식품 공공·빅데이터 활용 창업경진대회"),
    "ulsan_open_data_contest_entries": ("공공데이터·창업", "울산 공공데이터 활용 창업경진대회"),
    "gwangju_open_data_contest_awards": ("공공데이터·창업", "광주 공공데이터 활용 경진대회"),
    "kamco_data_contest_awards": ("공공데이터·창업", "한국자산관리공사 데이터 분야 공모전"),
    "youth_data_contest_awards": ("공공데이터·창업", "성평등가족부 데이터 경진대회"),
    "kaia_contest_submissions": ("산업·기술·농촌", "국토교통과학기술진흥원 공모전"),
    "happy_rural_community_awards": ("산업·기술·농촌", "행복농촌만들기 콘테스트"),
    "rural_sixth_industry_awards": ("산업·기술·농촌", "6차산업 경진대회"),
    "khnp_quality_circle_awards": ("산업·기술·농촌", "전국 품질분임조 경진대회(한수원)"),
    "fire_industry_technology_awards": ("산업·기술·농촌", "소방산업대상 공모전"),
    "serious_game_awards": ("산업·기술·농촌", "기능성게임 우수게임(콘진원)"),
    "software_teaching_case_awards": ("산업·기술·농촌", "SW 수업 우수사례 공모전"),
    "jeonnam_awarded_proposals": ("정책·행정 아이디어", "전남 우수제안"),
    "daejeon_junggu_policy_awards": ("정책·행정 아이디어", "대전 중구 정책제안 공모전"),
    "yeonggwang_contest_proposals": ("정책·행정 아이디어", "영광군 제안공모전"),
    "senior_employment_idea_awards": ("정책·행정 아이디어", "인천 노인일자리 아이디어 공모전"),
    "daegu_youth_budget_awards": ("정책·행정 아이디어", "대구 청소년 참여예산 우수사업"),
    "busan_urban_innovation_awards": ("정책·행정 아이디어", "부산도시공사 적극행정 우수사례"),
    "seoul_budget_proposals": ("주민참여예산", "서울시 시민참여예산"),
    "gwangjin_budget_proposals": ("주민참여예산", "서울 광진구 주민참여예산"),
    "yeongdeungpo_budget_proposals": ("주민참여예산", "서울 영등포구 주민참여예산"),
    "seodaemun_budget_proposals": ("주민참여예산", "서울 서대문구 주민참여예산"),
    "daegu_budget_project_proposals": ("주민참여예산", "대구시 주민참여예산"),
    "daegu_budget_selected_projects": ("주민참여예산", "대구시 주민참여예산"),
    "daegu_seogu_budget_proposals": ("주민참여예산", "대구 서구 주민참여예산"),
    "gwangju_budget_proposals": ("주민참여예산", "광주시 시민참여예산"),
    "gyeonggi_budget_proposals": ("주민참여예산", "경기도 주민참여예산"),
    "goyang_budget_proposals": ("주민참여예산", "고양시 주민참여예산"),
    "yangpyeong_budget_proposals": ("주민참여예산", "양평군 주민참여예산"),
    "ulsan_budget_proposals": ("주민참여예산", "울산시 주민참여예산"),
    "gyeongnam_budget_proposals": ("주민참여예산", "경남 주민참여예산"),
    "geoje_budget_proposals": ("주민참여예산", "거제시 주민참여예산"),
    "sejong_budget_proposals": ("주민참여예산", "세종시 주민제안사업"),
    "jeju_budget_proposals": ("주민참여예산", "제주 주민참여예산"),
    "chungbuk_budget_proposals": ("주민참여예산", "충북 주민참여예산"),
    "nonsan_district_budget_proposals": ("주민참여예산", "논산시 주민참여예산"),
    "nonsan_department_budget_proposals": ("주민참여예산", "논산시 주민참여예산"),
    "gyeongbuk_budget_proposals": ("주민참여예산", "경북 주민참여예산"),
    "busan_budget_proposals": ("주민참여예산", "부산시 주민참여예산"),
    "namdong_budget_proposals": ("주민참여예산", "인천 남동구 주민참여예산"),
    "yeonsu_budget_proposals": ("주민참여예산", "인천 연수구 주민참여예산"),
    "jeonbuk_budget_proposals": ("주민참여예산", "전북 주민참여예산"),
    "gangwon_budget_proposals": ("주민참여예산", "강원 주민참여예산"),
    "seoul_free_suggestions": ("상시 제안 창구", "상상대로 서울 자유제안"),
    "acrc_open_proposals": ("상시 제안 창구", "국민신문고 공개제안"),
    "seoul_law_proposals": ("상시 제안 창구", "서울시 법령·제도 개선 제안"),
    "yuseong_budget_proposals": ("상시 제안 창구", "대전 유성구 구민사업제안"),
    "jeonnam_citizen_proposals": ("상시 제안 창구", "소통인전남 제안광장"),
    "namdong_citizen_proposals": ("상시 제안 창구", "인천 남동구 구민제안"),
    "incheon_port_public_proposals": ("공공기관 국민제안", "인천항만공사 국민의견수렴"),
    "sejong_education_public_proposals": ("공공기관 국민제안", "세종시교육청 제안사업공모"),
    "kf_public_diplomacy_projects": ("공공기관 국민제안", "국제교류재단 국민공공외교프로젝트"),
    "family_support_public_proposals": ("공공기관 국민제안", "한국건강가정진흥원 국민제안"),
    "daejeon_transit_power_proposals": ("기관 내부 제안", "대전교통공사 제안(창안)"),
    "daejeon_transit_control_proposals": ("기관 내부 제안", "대전교통공사 제안(창안)"),
    "kogas_technology_research_proposals": ("기관 내부 제안", "한국가스기술공사 연구관리 제안"),
    "ai_education_teacher_projects": ("기관 내부 제안", "과학창의재단 AI교육 교사연구회 성과물"),
    "kps_employee_ideas": ("기관 내부 제안", "한전KPS 아이디어"),
    "incheon_facilities_public_ideas": ("기관 내부 제안", "인천시설공단 아이디어뱅크"),
}
BY_CONTEST = frozenset({"kipris_idea_api", "science_exhibition_archive_2015_onward",
                        "science_invention_archive_2015_onward", "science_museum_awards"})
UNCLASSIFIED = "미분류"


def contest_name(contest: str | None) -> str:
    return re.sub(r"제?\s*[0-9]+\s*회|[0-9]{4}년?|\s", "", contest or "")


def program_of(api: str, record_kind: str | None, contest: str | None) -> tuple[str, str, str]:
    field, name = PROGRAM.get(api, (UNCLASSIFIED, api))
    if api in BY_CONTEST and (c := contest_name(contest)):
        name = c
    return KIND.get(record_kind, UNCLASSIFIED), field, name

