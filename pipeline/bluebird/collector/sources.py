"""수집존(Z1) 파일 소스 어댑터.

현재 구현: 공공데이터포털 등에서 받은 파일을 수집존 반입 디렉터리(seed)에 두면 읽는 `awards_csv`, `kipris_idea_master`.
각 어댑터는 (source 메타, award_record 행 iterator)를 만든다. award_record에는 팀명·원천키가 없다.
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

    def meta_row(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "license": self.license,
            "url": self.url,
            "layer": self.layer,
            "public_ok": self.public_ok,
        }


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
