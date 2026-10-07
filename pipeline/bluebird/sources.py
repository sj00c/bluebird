"""원본 아이디어 파일 소스 어댑터.

파일은 backend-jobs의 seed 디렉터리(egress로 받은 것 또는 반입한 것)에 둔다. sources.toml이 소스 목록이다.
각 어댑터는 award_record 행 iterator를 만든다. award_record에는 팀명·성명·원천키가 없다(AWARD_RECORD_COLUMNS 고정).
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .anonymize import MASK, anon_id, audit_variants, mask_team, team_kind

_WS = re.compile(r"\s+")

AWARD_RECORD_COLUMNS = (
    "idea_id", "source_id", "contest_name", "host_org", "year", "award", "title", "body",
    "used_data", "category", "team_kind", "source_url", "extra",
)


@dataclass(frozen=True)
class SourceSpec:
    id: str
    adapter: str
    path: Path
    name: str
    license: str
    url: str
    layer: int
    public_ok: bool
    export_grade: str = "pending"
    policy_approved_by: str | None = None
    policy_approved_at: str | None = None


def load_sources(config: Path, seed_dir: Path) -> list[SourceSpec]:
    data = tomllib.loads(config.read_text(encoding="utf-8"))
    specs = []
    for s in data.get("source", []):
        if s["adapter"] not in ADAPTERS:
            raise ValueError(f"source {s['id']}: unknown adapter {s['adapter']!r}")
        specs.append(
            SourceSpec(
                id=s["id"],
                adapter=s["adapter"],
                path=seed_dir / s["file"],
                name=s["name"],
                license=s["license"],
                url=s.get("url", ""),
                layer=int(s["layer"]),
                public_ok=bool(s["public_ok"]),
                export_grade=s.get("export_grade", "pending"),
                policy_approved_by=s.get("policy_approved_by"),
                policy_approved_at=s.get("policy_approved_at"),
            )
        )
    return specs


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _norm(s: str | None) -> str:
    return _WS.sub(" ", (s or "").strip())


def _year(s: str) -> int | None:
    s = (s or "").strip()
    return int(s[:4]) if s[:4].isdigit() else None


def awards_csv(spec: SourceSpec, secret: bytes, names: dict[str, list[str]] | None = None) -> Iterator[dict]:
    """공공데이터 활용 창업경진대회 수상작(no, host, year, award, team, item, data, part)."""
    with spec.path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            team = r.get("team") or ""
            year = _year(r["year"])
            item = mask_team((r.get("item") or "").strip(), team)
            iid = anon_id(secret, spec.id, r["no"], year)
            _keep_names(names, iid, team)
            yield {
                "idea_id": iid,
                "source_id": spec.id,
                "contest_name": "범정부 공공데이터 활용 창업경진대회",
                "host_org": _norm(r.get("host")),
                "year": year,
                "award": _norm(r.get("award")) or None,
                "title": _norm(item.split("\n")[0])[:300],
                "body": item if "\n" in item or len(item) > 300 else None,
                "used_data": [_norm(x) for x in (r.get("data") or "").split("\n") if _norm(x)],
                "category": _norm(r.get("part")) if _norm(r.get("part")) not in ("", "-") else None,
                "team_kind": team_kind(team),
                "source_url": spec.url or None,
                "extra": {},
            }


def _host_from_institutions(inst: str) -> str:
    hosts = [p.split(":", 1)[1] for p in (inst or "").split(";") if p.startswith("주최:")]
    return ", ".join(hosts)


def kipris_idea_master(spec: SourceSpec, secret: bytes, names: dict[str, list[str]] | None = None) -> Iterator[dict]:
    """KIPRIS 공모전 아이디어 idea_master.csv(02_kipris_bulk 로더 산출물). 팀·개인 컬럼이 원래 없다."""
    with spec.path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            year = _year(r["CNTST_YEAR"])
            yield {
                "idea_id": anon_id(secret, spec.id, f"{r['CNTST_ID']}-{r['IDEA_SEQ']}", year),
                "source_id": spec.id,
                "contest_name": _norm(r["CNTST_NM"]),
                "host_org": _host_from_institutions(r.get("INSTITUTIONS", "")),
                "year": year,
                "award": _norm(r.get("AWARD_NM")) if _norm(r.get("AWARD_NM")) not in ("", "-") else None,
                "title": _norm(r["IDEA_NM"])[:300],
                "body": (r.get("IDEA_CONT_TXT") or "").strip() or None,
                "used_data": [],
                "category": _norm(r.get("TECH_CLSS")) or None,
                "team_kind": "empty",
                "source_url": _norm(r.get("ORGCP_DOC_URL")) or None,
                "extra": {
                    "ipc": [x for x in (r.get("IPC") or "").split(";") if x],
                    "patent_applno": [x for x in (r.get("PATENT_APPLNO") or "").split(";") if x],
                },
            }


def _keep_names(names: dict[str, list[str]] | None, idea_id: str, raw: str) -> None:
    """G10 성명 일치 감사용: 이 아이디어의 팀명·성명 형태를 호출자가 준 메모리 dict에만 담는다(DB·파일에 쓰지 않음)."""
    if names is not None and (v := audit_variants(raw)):
        names.setdefault(idea_id, []).extend(v)


def _read_csv(path: Path) -> list[dict]:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp949"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"{path.name}: neither utf-8 nor cp949")
    return list(csv.DictReader(io.StringIO(text, newline="")))


def _row_key(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).hexdigest()[:16]


class _StableKeys:
    """행 번호가 아니라 내용으로 원천키를 만든다(파일이 갱신·재정렬돼도 같은 행은 같은 ID).
    완전히 같은 내용이 여러 번 나오면 등장 순번만 붙인다."""

    def __init__(self):
        self._seen: dict[str, int] = {}

    def __call__(self, *parts: object) -> str:
        base = _row_key(*parts)
        k = self._seen.get(base, 0)
        self._seen[base] = k + 1
        return base if k == 0 else f"{base}#{k}"


# 원본 파일에 내용 대신 들어 있는 안내 문구. 본문·활용 데이터로 취급하지 않는다.
_PLACEHOLDERS = frozenset({"수정 내용 반영 예정", "-", "없음", "해당없음"})


def _text(s: str | None) -> str | None:
    s = (s or "").strip()
    return None if not s or _norm(s) in _PLACEHOLDERS else s


def _record(spec: SourceSpec, secret: bytes, key: str, **kw) -> dict:
    year = kw.get("year")
    rec = {
        "idea_id": anon_id(secret, spec.id, key, year), "source_id": spec.id, "contest_name": "", "host_org": "",
        "year": None, "award": None, "title": "", "body": None, "used_data": [], "category": None,
        "team_kind": "empty", "source_url": spec.url or None, "extra": {},
    }
    rec.update(kw)
    return rec


def startup_final_xlsx(spec: SourceSpec, secret: bytes, names: dict[str, list[str]] | None = None) -> Iterator[dict]:
    """범정부 공공데이터 활용 창업경진대회 본선 수상작(No., 수상연도, 회차, 수상내역, 참가팀, 아이템명, 서비스 내용, 활용 공공데이터, 비고)."""
    import openpyxl

    ws = openpyxl.load_workbook(spec.path, read_only=True, data_only=True).active
    rows = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(rows)]
    expect = ["No.", "수상연도", "회차", "수상내역", "참가팀(팀명)", "아이템명", "서비스 내용", "활용 공공데이터(기관)", "비고"]
    if header[: len(expect)] != expect:
        raise ValueError(f"{spec.path.name}: unexpected header {header}")
    key = _StableKeys()
    for raw in rows:
        r = dict(zip(expect, (str(v).strip() if v is not None else "" for v in raw)))
        if not r["아이템명"]:
            continue
        team = r["참가팀(팀명)"]
        year = _year(r["수상연도"])
        body = _text(mask_team(r["서비스 내용"], team))
        used = _text(r["활용 공공데이터(기관)"]) or ""
        rec = _record(
            spec, secret, key(year, _norm(r["수상내역"]), _norm(r["아이템명"])),
            contest_name="범정부 공공데이터 활용 창업경진대회(본선)", host_org="행정안전부", year=year,
            award=_norm(r["수상내역"]) or None,
            title=_norm(mask_team(r["아이템명"], team))[:300],
            body=body,
            used_data=[_norm(x) for x in re.split(r"[,\n]", used) if _norm(x)],
            category=_norm(r["비고"]) or None,
            team_kind=team_kind(team),
        )
        _keep_names(names, rec["idea_id"], team)
        yield rec


def science_museum_csv(spec: SourceSpec, secret: bytes, names: dict[str, list[str]] | None = None) -> Iterator[dict]:
    """국립중앙과학관 수상작(대회명, 주제, 소속명, 제목, 지도교사, 수상자, 수상명).

    지도교사·수상자(성명)·소속명(학교)은 레코드에 넣지 않는다. 이름은 제목 마스킹과 G10 감사(names, 메모리)에만 쓴다.
    """
    key = _StableKeys()
    for r in _read_csv(spec.path):
        contest = _norm(r["대회명"])
        title = _norm(r["제목"])
        if not title:
            continue
        people = [n for n in re.split(r"[,\s]+", f"{r.get('수상자', '')} {r.get('지도교사', '')}") if len(n) >= 2]
        for name in people:
            title = title.replace(name, MASK)
        m = re.search(r"제\s*(\d+)\s*회", contest)
        n = int(m.group(1)) if m else None
        # 파일 기준일 2024-09-09 기준 최신 회차: 제69회 전국과학전람회(2023), 제44회 전국학생과학발명품경진대회(2022).
        year = (1954 + n if n and "과학전람회" in contest
                else 1978 + n if n and "발명품" in contest else None)
        award = _norm(r.get("수상명"))
        rec = _record(
            spec, secret, key(contest, title, award),
            contest_name=contest, host_org="국립중앙과학관", year=year,
            award=award if award and award != "등급외" else None, title=title[:300],
            category=_norm(r.get("주제")) or None, team_kind="masked",
        )
        for name in people:
            _keep_names(names, rec["idea_id"], name)
        yield rec


def mafra_contest_csv(spec: SourceSpec, secret: bytes, names: dict[str, list[str]] | None = None) -> Iterator[dict]:
    """농식품 공공·빅데이터 활용 창업경진대회(경진대회명, 분야_포상, 작품명, 활용 공공데이터명, 데이터 등록일)."""
    key = _StableKeys()
    for r in _read_csv(spec.path):
        title = _norm(r["작품명"])
        if not title:
            continue
        contest = _norm(r["경진대회명"])
        part, _, award = _norm(r["분야_포상"]).partition("/")
        yield _record(
            spec, secret, key(contest, _norm(r["분야_포상"]), title),
            contest_name=f"농식품 공공·빅데이터 활용 {contest}", host_org="농림축산식품부",
            year=_year(contest), award=_norm(award) or None, title=title[:300],
            used_data=[_norm(x) for x in r["활용 공공데이터명"].split(",") if _norm(x)],
            category=_norm(part) or None,
        )


def design_idea_csv(spec: SourceSpec, secret: bytes, names: dict[str, list[str]] | None = None) -> Iterator[dict]:
    """공공디자인 국민아이디어공모 수상작(등록번호, 연도, 포상, 수상자, 제목, 내용). 수상자 성명은 레코드에 넣지 않고
    본문 마스킹과 G10 감사(names, 메모리)에만 쓴다."""
    for r in _read_csv(spec.path):
        name = _norm(r.get("수상자"))
        title = _norm(mask_team(r["제목"], name))
        if not title:
            continue
        body = mask_team((r.get("내용") or "").strip(), name)
        year = _year(r["연도"])
        rec = _record(
            spec, secret, r["등록번호"].strip(),
            contest_name="공공디자인 국민아이디어공모", host_org="한국공예디자인문화진흥원", year=year,
            award=_norm(r.get("포상")) or None, title=title[:300],
            body=body if body and _norm(body) != title else None,
            team_kind="masked",
        )
        _keep_names(names, rec["idea_id"], name)
        yield rec


ADAPTERS = {
    "awards_csv": awards_csv,
    "kipris_idea_master": kipris_idea_master,
    "startup_final_xlsx": startup_final_xlsx,
    "science_museum_csv": science_museum_csv,
    "mafra_contest_csv": mafra_contest_csv,
    "design_idea_csv": design_idea_csv,
}
