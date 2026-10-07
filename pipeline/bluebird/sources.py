"""원본 아이디어 파일 소스 어댑터.

파일은 backend-jobs의 seed 디렉터리(egress로 받은 것 또는 반입한 것)에 둔다. sources.toml이 소스 목록이다.
각 어댑터는 award_record 행 iterator를 만든다. award_record에는 팀명·성명·원천키가 없다(AWARD_RECORD_COLUMNS 고정).
"""

from __future__ import annotations

import csv
import hashlib
import re
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .anonymize import anon_id, mask_team, team_kind

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


def awards_csv(spec: SourceSpec, secret: bytes) -> Iterator[dict]:
    """공공데이터 활용 창업경진대회 수상작(no, host, year, award, team, item, data, part)."""
    with spec.path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            team = r.get("team") or ""
            year = _year(r["year"])
            item = mask_team((r.get("item") or "").strip(), team)
            yield {
                "idea_id": anon_id(secret, spec.id, r["no"], year),
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


def kipris_idea_master(spec: SourceSpec, secret: bytes) -> Iterator[dict]:
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


ADAPTERS = {"awards_csv": awards_csv, "kipris_idea_master": kipris_idea_master}
