"""raw → master 정제(parangsae). 규칙 기반, LLM 없음.

- 소스별 추출: title·body·contest·url·year. 등록 매핑([source.columns]) 소스 = 매핑 그대로, 나머지 = 아래 고정 추출기
- 글머리 정리: 섹션 라벨([제안취지] 등) 유지. 글머리 기호·깨진 문자(사설 영역)·줄 앞뒤 짝 없는 따옴표·제목 앞 접수번호 제거, 공백 하나로
- 개인정보: 전화·이메일·'제안자 홍길동' 고정 치환, 매핑된 성명·팀명 → [이름]
- contest = 원본 행에 있을 때만(레지스트리 기본값으로 채우지 않음). master에는 저장 안 함 → kind·field·program 계산에만(programs.py)
- url = 행 URL, 없으면 레지스트리 출처 URL
- 재실행: 기본 칸만 갱신, raw에서 빠진 행 삭제. 제목·본문이 바뀐 행 = AI 칸(label~verified) 비움 → 다음 extract가 다시 판정
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from urllib.parse import urlsplit

from . import db, programs
from .anonymize import MASK, mask_contacts, mask_team
from .collect_kipris import LINK_HOSTS
from .collect_proposals import _ACRC_SECTIONS, _SEOUL_SECTIONS

Fields = dict   # title, body, contest, url, year
Extract = Callable[[dict], Fields | None]

NAME = "[이름]"
_NULL = frozenset({"", "[NULL]", "-", "없음", "해당없음", "수정 내용 반영 예정"})
# 깨진 문자 = 사설 영역(한글 문서 전용 기호 등) + 제어문자(탭·줄바꿈 제외) + 대체 문자
_BROKEN = re.compile("[\ue000-\uf8ff\U000f0000-\U0010ffff\x00-\x08\x0b\x0c\x0e-\x1f\ufffd]")
# 글머리 기호: 어디서든 제거되는 것(문장 안 쓰임 없음)
_BULLETS = re.compile(r"[○●◎◦▪▫■□◆◇▶▷►▸•※☞➢➤✔✓❍❏]")
# 줄 앞 글머리: '-', '·', 'ㆍ', '*', '+'(문장 중간의 하이픈·가운뎃점은 유지)
_LEAD = re.compile(r"^[\s\-–—·ㆍ*+]+(?=\S)")
# 제목 앞 접수번호: (SPS-2607-3012689) 같은 영문 코드-숫자 묶음
_RECEIPT = re.compile(r"^\s*[(\[]?[A-Z]{2,5}(?:-\d{2,}){2,}[)\]]?\s*")
_YEAR = re.compile(r"(?:19|20)\d{2}(?!\d)")
_YY = re.compile(r"^\(?'?(\d{2})년")   # '21년 상반기', "('22년) 감자밭" = 2000년대 두 자리
# HTML 줄바꿈: <br>, <br />, 대구 원본의 태그 없는 'br'(한글 사이) → 줄바꿈. 그 밖 서식 태그 = 제거
_BR = re.compile(r"<br\s*/?>|(?<=[가-힣.,:)])br(?=[가-힣(\[])", re.IGNORECASE)
_TAG = re.compile(r"</?(?:p|div|span|font|b|strong|u|i|o:p)\b[^>]*>", re.IGNORECASE)
# 깨진 기호 '?'(원본 ○·▷ 글머리, 가운뎃점 ·). 물음표로 끝날 수 있는 글자 뒤면 진짜 물음표로 보고 유지
_Q_END = frozenset("까요죠가냐래니지나오야데는고어게")
_Q_SPACED = re.compile(r"(\S) \?(?= )")        # '지원 ? 독거남' = 글머리
# '측정?분석' = 가운뎃점. 뒤가 조사(에·를·을·라·로·와·과)면 깨진 따옴표('탐구?에 대한')일 수 있어 유지
_Q_JOINED = re.compile(r"([가-힣])\?(?=[가-힣])(?![에를을라로와과])")


def _val(value) -> str:
    text = html.unescape(html.unescape(str(value if value is not None else ""))).strip()   # &amp;lt; 이중 이스케이프
    return "" if text in _NULL else text


def _line(line: str) -> str:
    line = _BULLETS.sub(" ", line).strip()
    line = re.sub(r"^\?+\s*", "", line)   # 줄 앞 '?' = 글머리
    line = _Q_SPACED.sub(lambda m: m.group(0) if m.group(1) in _Q_END else m.group(1), line)
    line = _Q_JOINED.sub(lambda m: m.group(0) if m.group(1) in _Q_END else m.group(1) + "·", line)
    if line.count('"') % 2:   # 짝 없는 따옴표(원본 셀 따옴표 잔재) = 줄 앞·끝만
        line = line.removeprefix('"').removesuffix('"').strip()
    return _LEAD.sub("", line).strip()


def clean(text: str | None, *, title: bool = False) -> str:
    """글머리 정리. 섹션 라벨은 그대로 남는다."""
    text = _BROKEN.sub("", _val(text)).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[^\S\n]+", " ", _TAG.sub("", _BR.sub("\n", text)))   # NBSP 등 공백 통일
    out = " ".join(x for x in (_line(line) for line in text.split("\n")) if x)
    out = re.sub(r'"{2,}', '"', " ".join(out.split()))   # CSV 이중 따옴표 잔재
    if title:
        out = _LEAD.sub("", _RECEIPT.sub("", out)).rstrip("* ")   # 접수번호 뒤 *강조* 표시
    return out


def _mask(text: str, people: list[str] = ()) -> str:
    """정리 후 적용(정리가 ○를 지우므로 마스킹 토큰은 [이름])."""
    if not text:
        return text
    for person in people:
        if _val(person):
            text = mask_team(text, person)
    return (mask_contacts(text) or "").replace(MASK, NAME)


def _year(value) -> int | None:
    text = _val(value)
    if m := _YEAR.match(text):
        return int(m.group(0))
    return 2000 + int(m.group(1)) if (m := _YY.match(text)) else None


def _sections(row: dict, parts: list[tuple[str, list[str] | str]]) -> str:
    """[라벨] + 분할 필드 연결(구분자 없음, 원본이 긴 글을 여러 필드로 나눔). 빈 섹션 생략."""
    out = []
    for label, fields in parts:
        names = [fields] if isinstance(fields, str) else fields
        text = clean("".join(_val(row.get(f)) for f in names))
        if text:
            out.append(f"[{label}] {text}")
    return " ".join(out)


def _fields(title: str, body: str = "", *, contest: str = "", url: str = "", year: int | None = None,
            people: list[str] = ()) -> Fields | None:
    title = _mask(clean(title, title=True), people)
    if not title:
        return None
    body = _mask(body, people)
    return {"title": title, "body": body if body and body != title else None,
            "contest": clean(contest) or None, "url": _val(url) or None, "year": year}


# ---------------------------------------------------------------- 등록 매핑 소스

# 레지스트리가 본문을 매핑하지 않은 소스의 본문 열(master 전용).
# 레지스트리에 넣으면 key 열 없는 소스의 core 원천키(내용 해시)가 바뀜 → 여기서만. 댓글·주소·진행상황 = 제외.
EXTRA_BODY: dict[str, list[str]] = {
    "daegu_budget_project_proposals": ["사업목적", "사업효과"],
    "daegu_budget_selected_projects": ["사업개요"],
    "family_support_public_proposals": ["국민 제안 내용"],
    "incheon_port_public_proposals": ["추진배경", "제안내용", "기대효과"],
    "jeonnam_citizen_proposals": ["공개내용"],
    "sejong_education_public_proposals": ["사업필요성설명", "사업설명", "추진방법설명", "기대효과설명"],
    "yeonggwang_contest_proposals": ["게시물 내용(BS_CONTENT)"],
}

# 레지스트리에 연도 열이 없는 소스의 연도 열(master 전용, 이유 = EXTRA_BODY와 같음)
EXTRA_YEAR: dict[str, str] = {"rural_sixth_industry_awards": "제목"}   # 제목 앞 ('22년)

# 수상 등급 열(raw payload 헤더). 원본 값 그대로(등급외·선정 등 포함). 수상자·시상금·훈격·분야 열 = 제외.
AWARD: dict[str, str] = {
    "busan_urban_innovation_awards": "구분",
    "daegu_youth_budget_awards": "수상이름",
    "daejeon_junggu_policy_awards": "등급",
    "fire_industry_design_awards": "수상구분",
    "fire_industry_technology_awards": "수상구분",
    "gov_startup_final_awards": "수상내역",
    "gov_startup_prelim_awards": "award",
    "gwangju_open_data_contest_awards": "수상구분",
    "happy_rural_community_awards": "수상등급",
    "jeonnam_awarded_proposals": "등급",
    "kamco_data_contest_awards": "수상내역",
    "khnp_quality_circle_awards": "수상내역",
    "kidp_good_design_projects": "award",
    "kidp_korea_design_projects": "award",
    "kidp_youth_design_projects": "award",
    "kipris_idea_api": "awardInformation",
    "mafra_agrifood_contest": "분야_포상",
    "science_exhibition_archive_2015_onward": "award",
    "science_invention_archive_2015_onward": "award",
    "science_museum_awards": "수상명",
    "senior_employment_idea_awards": "수상내역",
    "serious_game_awards": "수상구분",
    "youth_data_contest_awards": "수상명(WNAWD_NM)",
}


def award(source: str, payload: dict) -> str | None:
    if source not in AWARD:
        return None
    return " ".join(_val(payload.get(AWARD[source])).split()) or None


def mapped(spec: dict) -> Extract:
    """[source.columns] = 원본 헤더 매핑. 안내 행(require_any·row_equals·exclude)·반복 헤더 행 제외."""
    columns = {**spec["columns"]}
    columns["body"] = [*columns.get("body", []), *EXTRA_BODY.get(spec["id"], [])]
    scalar = {k: v for k, v in columns.items() if k not in ("body", "people")}
    excluded = {h: {" ".join(v.split()) for v in values} for h, values in spec.get("exclude", {}).items()}

    def extract(row: dict) -> Fields | None:
        if all(row.get(h) == h for h in scalar.values()):
            return None
        if spec.get("require_any") and not any(_val(row.get(h)) for h in spec["require_any"]):
            return None
        if any(" ".join(_val(row.get(h)).split()) != " ".join(v.split()) for h, v in spec.get("row_equals", {}).items()):
            return None
        if any(" ".join(_val(row.get(h)).split()) in values for h, values in excluded.items()):
            return None
        body = " ".join(x for h in columns.get("body", []) if (x := clean(row.get(h))))
        url = _val(row.get(columns["source_url"])) if "source_url" in columns else ""
        return _fields(row.get(columns["title"]), body, contest=row.get(columns.get("contest", ""), ""),
                       url=url or spec.get("url", ""),
                       year=_year(row.get(columns.get("year", ""))) or _year(row.get(EXTRA_YEAR.get(spec["id"], ""))),
                       people=[row.get(h, "") for h in columns.get("people", [])])
    return extract


# ---------------------------------------------------------------- 고정 추출기(시드 파일·API)

def _awards(spec: dict) -> Extract:
    """창업경진대회 예선 수상작(no, host, year, award, team, item, data, part). item 첫 줄 = 제목, 나머지 = 본문."""
    def extract(r: dict) -> Fields | None:
        first, _, rest = _val(r.get("item")).partition("\n")
        return _fields(first, clean(rest), url=spec["url"], year=_year(r.get("year")), people=[r.get("team", "")])
    return extract


def _startup_final(spec: dict) -> Extract:
    def extract(r: dict) -> Fields | None:
        return _fields(r.get("아이템명"), clean(r.get("서비스 내용")), url=spec["url"],
                       year=_year(r.get("수상연도")), people=[r.get("참가팀(팀명)", "")])
    return extract


def _science_museum(spec: dict) -> Extract:
    """대회명 회차 → 연도(과학전람회 = 1954+회, 발명품경진대회 = 1978+회)."""
    def extract(r: dict) -> Fields | None:
        contest = _val(r.get("대회명"))
        m = re.search(r"제\s*(\d+)\s*회", contest)
        n = int(m.group(1)) if m else None
        year = 1954 + n if n and "과학전람회" in contest else 1978 + n if n and "발명품" in contest else None
        people = re.split(r"[,\s]+", f"{r.get('수상자', '')} {r.get('지도교사', '')}")
        return _fields(r.get("제목"), contest=contest, url=spec["url"], year=year,
                       people=[p for p in people if len(p) >= 2])
    return extract


def _mafra(spec: dict) -> Extract:
    def extract(r: dict) -> Fields | None:
        contest = _val(r.get("경진대회명"))
        return _fields(r.get("작품명"), contest=contest, url=spec["url"], year=_year(contest))
    return extract


def _design_idea(spec: dict) -> Extract:
    def extract(r: dict) -> Fields | None:
        return _fields(r.get("제목"), clean(r.get("내용")), url=spec["url"], year=_year(r.get("연도")),
                       people=[r.get("수상자", "")])
    return extract


def _seoul_budget(spec: dict) -> Extract:
    def extract(r: dict) -> Fields | None:
        return _fields(r.get("BIZ_NM"), _sections(r, _SEOUL_SECTIONS), url=spec["url"], year=_year(r.get("FIS_YEAR")))
    return extract


def _seoul_law(spec: dict) -> Extract:
    def extract(r: dict) -> Fields | None:
        body = _sections(r, [("현황및문제점", ["CONTROVERSIAL"]), ("개선방안", ["IMPROVEMENT"])])
        return _fields(r.get("TITLE"), body, url=spec["url"], year=_year(r.get("RDATE")))
    return extract


def _seoul_free(spec: dict) -> Extract:
    """본문 없음. CONTENT = 공식 상세 페이지 URL."""
    def extract(r: dict) -> Fields | None:
        link = _val(r.get("CONTENT"))
        ok = urlsplit(link).hostname == "idea.seoul.go.kr"
        return _fields(r.get("TITLE"), url=link if ok else spec["url"], year=_year(r.get("REG_DATE")))
    return extract


def _gg(spec: dict) -> Extract:
    """본문 없음(사업명·구분·지역·선정 여부만)."""
    def extract(r: dict) -> Fields | None:
        return _fields(r.get("BIZ_NM"), url=spec["url"], year=_year(r.get("RCPT_YR")))
    return extract


def _acrc(spec: dict) -> Extract:
    """상세(resultData) 또는 목록 항목(상세 없음 = 제목만, 목록 제목은 '..'로 잘림). 제안자 성명 = 마스킹 대상."""
    def extract(r: dict) -> Fields | None:
        return _fields(r.get("title"), _sections(r, _ACRC_SECTIONS), url=spec["url"],
                       year=_year(r.get("regDate")), people=[r.get("peterName", "")])
    return extract


# KIPRIS 본문 소제목 줄(발명내용·용도 및 효과 등) → '[소제목]'(다른 소스 섹션 라벨과 같은 형식)
_KIPRIS_LABELS = frozenset({"발명내용", "용도 및 효과", "발명동기", "발명의 동기", "발명 효과", "발명의 효과", "작품설명",
                            "개발내용", "목적", "기대효과", "효과", "용도", "발명품 설명"})


def _kipris_body(text: str | None) -> str:
    lines = _BR.sub("\n", _val(text)).split("\n")
    out = []
    for line in lines:
        s = line.strip()
        if m := re.fullmatch(r"\[\s*(.+?)\s*\]", s):
            s = f"[{m.group(1)}]"
        elif s in _KIPRIS_LABELS:
            s = f"[{s}]"
        out.append(s)
    return clean("\n".join(out))


def _kipris(spec: dict) -> Extract:
    def extract(r: dict) -> Fields | None:
        link = _val(r.get("originalLink"))
        return _fields(r.get("ideaName"), _kipris_body(r.get("ideaContent")), contest=r.get("contestName", ""),
                       url=link if urlsplit(link).hostname in LINK_HOSTS else spec["url"],
                       year=_year(r.get("contestYear")))
    return extract


BY_ADAPTER: dict[str, Callable[[dict], Extract]] = {
    "awards_csv": _awards, "startup_final_xlsx": _startup_final, "science_museum_csv": _science_museum,
    "mafra_contest_csv": _mafra, "design_idea_csv": _design_idea,
}
# raw source id → 추출기. seoul_budget_selected = 접수 건의 선정 정보(같은 제안) → master 행 없음.
BY_SOURCE: dict[str, Callable[[dict], Extract]] = {
    "seoul_budget_proposals": _seoul_budget, "seoul_law_proposals": _seoul_law,
    "seoul_free_suggestions": _seoul_free, "gyeonggi_budget_proposals": _gg,
    "acrc_open_proposals": _acrc, "kipris_idea_api": _kipris,
}
SKIP = frozenset({"seoul_budget_selected"})


def extractor(spec: dict) -> Extract:
    if spec["id"] in BY_SOURCE:
        return BY_SOURCE[spec["id"]](spec)
    if spec.get("adapter") in BY_ADAPTER:
        return BY_ADAPTER[spec["adapter"]](spec)
    if spec.get("columns", {}).get("title"):
        return mapped(spec)
    raise ValueError(f"source {spec['id']}: no extractor")


AI_COLS = ("label", "item_type", "goal", "solution", "features", "domain", "evidence", "verified")
_TEXT_CHANGED = "master.title IS DISTINCT FROM EXCLUDED.title OR master.body IS DISTINCT FROM EXCLUDED.body"


def refine(*, dsn: str, sources: list[dict], only: str | None = None) -> list[dict]:
    specs = {s["id"]: s for s in sources}
    results = []
    with db.connect(dsn) as conn:
        present = [s for (s,) in conn.execute("SELECT DISTINCT source FROM raw ORDER BY 1")]
        for source in present:
            if (only and source != only) or source in SKIP or source.endswith(".detail"):
                continue
            if source not in specs:
                results.append({"source": source, "status": "error", "error": "not in registry"})
                continue
            extract = extractor(specs[source])
            kind = specs[source].get("record_kind")
            rows, dropped = [], 0
            # 상세 페이지 본문(master.load_detail) = 목록 본문 뒤에 이어 붙임
            for key, payload, detail in conn.execute(
                    "SELECT r.key, r.payload, d.payload->>'body' FROM raw r"
                    " LEFT JOIN raw d ON d.source = r.source || '.detail' AND d.key = r.key"
                    " WHERE r.source = %s", (source,)):
                f = extract(payload)
                if f is None:
                    dropped += 1
                    continue
                if extra := _mask(clean(detail)):
                    body = " ".join(x for x in (f["body"], extra) if x)
                    f["body"] = body if body != f["title"] else None
                rows.append((source, key, f["title"], f["body"], *programs.program_of(source, kind, f["contest"]),
                             award(source, payload), f["url"], f["year"]))
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO master (api, key, title, body, kind, field, program, award, url, year)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    " ON CONFLICT (api, key) DO UPDATE SET title = EXCLUDED.title, body = EXCLUDED.body,"
                    " kind = EXCLUDED.kind, field = EXCLUDED.field, program = EXCLUDED.program,"
                    " award = EXCLUDED.award, url = EXCLUDED.url, year = EXCLUDED.year, "
                    + ", ".join(f"{c} = CASE WHEN {_TEXT_CHANGED} THEN NULL ELSE master.{c} END" for c in AI_COLS)
                    # 안 바뀐 행 = 쓰지 않음(전체 재기록 = 큰 WAL)
                    + " WHERE (master.title, master.body, master.kind, master.field, master.program, master.award,"
                    " master.url, master.year) IS DISTINCT FROM (EXCLUDED.title, EXCLUDED.body, EXCLUDED.kind,"
                    " EXCLUDED.field, EXCLUDED.program, EXCLUDED.award, EXCLUDED.url, EXCLUDED.year)",
                    rows)
                cur.execute("CREATE TEMP TABLE IF NOT EXISTS keep (key text PRIMARY KEY) ON COMMIT DELETE ROWS")
                cur.executemany("INSERT INTO keep VALUES (%s)", [(r[1],) for r in rows])
                removed = cur.execute("DELETE FROM master m WHERE api = %s AND NOT EXISTS"
                                      " (SELECT 1 FROM keep k WHERE k.key = m.key)", (source,)).rowcount
            conn.commit()
            results.append({"source": source, "status": "ok", "rows": len(rows), "dropped": dropped,
                            "removed": removed, "unclassified": sum(programs.UNCLASSIFIED in r[4:6] for r in rows)})
    return results
