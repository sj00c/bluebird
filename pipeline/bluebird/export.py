"""공유용 내보내기.

- xlsx      : 아이디어 전체(선별 재료 포함)를 엑셀 한 파일로. 기본은 라이선스상 외부 공유가 가능한 소스만,
              --include-held 를 켜면 "공개·외부 전송 보류" 소스도 넣는다(받는 쪽이 책임지는 내부 공유용).
- provenance: 어느 소스에서 무엇을 언제 얼마나 받았는지 — DB(core.source·ingest_run·idea)와 레지스트리(TOML)에서 생성한 Markdown.

둘 다 읽기만 한다. 공개 승인·깔때기 상태와 무관하게 core 전체를 다룬다(공유 판단은 라이선스 열로 한다).
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from . import db
from .sources import load_sources

# 소스 라이선스 문구에 이 말이 들어 있으면 외부 공유 보류로 본다(레지스트리 license 필드가 기준).
HELD_PATTERN = re.compile(r"보류|재확인 필요|All Rights Reserved")

IDEA_COLS = ("id", "source_id", "source_name", "license", "share", "record_kind", "contest", "host_org", "audience",
             "year", "award", "title", "body", "category", "used_data", "source_url", "exclude_reasons")

IDEA_SQL = """
SELECT i.id, s.id, s.name, s.license, s.record_kind, coalesce(nullif(c.name, ''), s.name), c.host_org, c.audience,
       i.year, i.award, i.title, i.body, i.category, array_to_string(i.used_data, '; '), i.source_url,
       (SELECT string_agg(x.reason, ', ' ORDER BY x.reason) FROM core.idea_exclusion x WHERE x.idea_id = i.id)
  FROM core.idea i
  JOIN core.source s ON s.id = i.source_id
  JOIN core.contest c ON c.id = i.contest_id
 WHERE i.retired_at IS NULL AND i.withheld_at IS NULL {held}
 ORDER BY s.id, i.year NULLS LAST, i.id
"""

SOURCE_SQL = """
SELECT s.id, s.name, s.license, s.url, s.record_kind, s.exclude_reason,
       coalesce(i.n, 0), i.y0, i.y1, coalesce(i.with_body, 0), r.first_at, r.last_at
  FROM core.source s
  LEFT JOIN (SELECT source_id, count(*) n, min(year) y0, max(year) y1, count(body) with_body
               FROM core.idea WHERE retired_at IS NULL GROUP BY 1) i ON i.source_id = s.id
  LEFT JOIN (SELECT source_id, min(started_at)::date first_at, max(started_at)::date last_at
               FROM core.ingest_run WHERE status = 'ok' GROUP BY 1) r ON r.source_id = s.id
 ORDER BY coalesce(i.n, 0) DESC
"""


def _held(license_text: str) -> bool:
    return bool(HELD_PATTERN.search(license_text or ""))


def _autosize(ws, widths: dict[str, int]):
    for idx, cell in enumerate(ws[1], start=1):
        ws.column_dimensions[get_column_letter(idx)].width = widths.get(cell.value, 14)
    ws.freeze_panes = "A2"


def xlsx(*, dsn: str, out: Path, include_held: bool = False) -> dict:
    with db.connect(dsn) as conn:
        sources = conn.execute(SOURCE_SQL).fetchall()
        held_ids = {r[0] for r in sources if _held(r[2])}
        clause = "" if include_held else "AND NOT (s.id = ANY(%s))"
        params = () if include_held else ([*held_ids],)
        ideas = conn.execute(IDEA_SQL.format(held=clause), params).fetchall()
        reasons = conn.execute("SELECT code, label, basis, note FROM core.exclusion_reason ORDER BY code").fetchall()
        reason_counts = dict(conn.execute("SELECT reason, count(*) FROM core.idea_exclusion GROUP BY 1").fetchall())
        contests = conn.execute(
            """SELECT c.id, c.source_id, c.name, c.host_org, c.year, c.audience, count(i.id)
                 FROM core.contest c LEFT JOIN core.idea i ON i.contest_id = c.id AND i.retired_at IS NULL
                GROUP BY c.id ORDER BY count(i.id) DESC""").fetchall()

    wb = Workbook()
    ws = wb.active
    ws.title = "읽어주세요"
    today = dt.date.today().isoformat()
    shared = [r for r in sources if include_held or r[0] not in held_ids]
    n_ideas = len(ideas)
    lines = [
        ("파랑새 아이디어 데이터 공유본", ""),
        ("생성일", today),
        ("아이디어 건수", n_ideas),
        ("소스 수", len(shared)),
        ("보류 소스 포함", "예 — 받는 쪽이 라이선스 책임" if include_held else "아니오 — 외부 공유 가능 소스만"),
        ("", ""),
        ("시트", "내용"),
        ("ideas", "아이디어 1건 = 1행. share 열이 '보류'면 외부 재배포 금지(원 기관 약관 확인 전)."),
        ("sources", "소스별 출처 URL·라이선스·건수·연도·받은 날짜"),
        ("contests", "대회별 건수와 대상자(student = 초·중·고 학생 대회)"),
        ("exclusion_reason", "ideas.exclude_reasons 열의 코드 뜻. 제외 '후보' 이유일 뿐 걸러내지 않았다."),
        ("", ""),
        ("주의", "수상자·제안자 이름은 적재 때 제거했다(team_kind 마스킹). 본문에 남은 이름은 원 기관 공개본 그대로다."),
        ("주의", "exclude_reasons 가 빈 행 = 지금까지 찾은 어떤 제외 근거에도 걸리지 않은 아이디어."),
    ]
    for a, b in lines:
        ws.append([a, b])
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 100

    ws = wb.create_sheet("ideas")
    ws.append(list(IDEA_COLS))
    for r in ideas:
        sid, lic = r[1], r[3]
        share = "보류" if sid in held_ids else "가능"
        ws.append([r[0], sid, r[2], lic, share, r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12], r[13], r[14],
                   r[15] or ""])
    _autosize(ws, {"id": 22, "source_id": 30, "source_name": 40, "license": 30, "share": 6, "record_kind": 18,
                   "contest": 30, "host_org": 20, "audience": 9, "year": 6, "award": 12, "title": 50, "body": 80,
                   "category": 14, "used_data": 30, "source_url": 40, "exclude_reasons": 30})

    ws = wb.create_sheet("sources")
    ws.append(["source_id", "name", "share", "license", "url", "record_kind", "exclude_reason", "ideas",
               "year_min", "year_max", "with_body", "first_ingest", "last_ingest"])
    for r in shared:
        ws.append([r[0], r[1], "보류" if r[0] in held_ids else "가능", r[2], r[3], r[4], r[5] or "", r[6], r[7], r[8],
                   r[9], str(r[10] or ""), str(r[11] or "")])
    _autosize(ws, {"source_id": 36, "name": 50, "license": 40, "url": 50, "record_kind": 20})

    ws = wb.create_sheet("contests")
    ws.append(["contest_id", "source_id", "name", "host_org", "year", "audience", "ideas"])
    for r in contests:
        if include_held or r[1] not in held_ids:
            ws.append(list(r))
    _autosize(ws, {"contest_id": 20, "source_id": 36, "name": 50, "host_org": 24})

    ws = wb.create_sheet("exclusion_reason")
    ws.append(["code", "label", "basis", "note", "ideas"])
    for code, label, basis, note in reasons:
        ws.append([code, label, basis, note, reason_counts.get(code, 0)])
    _autosize(ws, {"code": 22, "label": 28, "basis": 9, "note": 80})

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return {"path": str(out), "ideas": n_ideas, "sources": len(shared), "held_excluded": sorted(held_ids - {r[0] for r in shared})}


def provenance(*, dsn: str, configs: list[Path], out: Path) -> dict:
    """소스 출처 명세 Markdown. 레지스트리(수집 방식·데이터셋 id·열 매핑 유무)와 DB(건수·연도·받은 날짜)를 합친다."""
    specs = {}
    for cfg in configs:
        for s in load_sources(cfg, Path("/nonexistent")):
            specs[s.id] = (s, cfg.name)
    with db.connect(dsn) as conn:
        rows = conn.execute(SOURCE_SQL).fetchall()
        total = conn.execute("SELECT count(*) FROM core.idea WHERE retired_at IS NULL").fetchone()[0]
        kinds = dict(conn.execute(
            """SELECT s.record_kind, count(*) FROM core.idea i JOIN core.source s ON s.id = i.source_id
                WHERE i.retired_at IS NULL GROUP BY 1""").fetchall())
        audience = dict(conn.execute(
            """SELECT c.audience, count(*) FROM core.idea i JOIN core.contest c ON c.id = i.contest_id
                WHERE i.retired_at IS NULL GROUP BY 1""").fetchall())
        reasons = conn.execute(
            """SELECT r.code, r.label, count(x.idea_id) FROM core.exclusion_reason r
                 LEFT JOIN core.idea_exclusion x ON x.reason = r.code GROUP BY 1, 2 ORDER BY 3 DESC""").fetchall()

    def how(sid: str) -> str:
        s = specs.get(sid)
        if not s:
            return "레지스트리에 없음(DB에만 남은 소스)"
        spec, cfg = s
        if spec.collector:
            return f"`{cfg}` · 수집기 `{spec.collector}`" + (f" · 데이터셋 {spec.dataset_id}" if spec.dataset_id else "")
        return f"`{cfg}` · 파일 `{Path(spec.path).name}` · 어댑터 `{spec.adapter}`"

    kind_label = {"contest_award": "수상작", "contest_submission": "출품작", "public_proposal": "국민·주민 제안",
                  "improvement_proposal": "직원 개선제안", None: "미기재"}
    held = [r for r in rows if _held(r[2])]
    md = [f"# 데이터 출처 명세", "",
          f"생성 {dt.date.today().isoformat()} — `bluebird export provenance` 가 DB와 레지스트리에서 만든다. 손으로 고치지 말고 다시 생성한다.", "",
          f"아이디어 **{total:,}건**, 소스 {len(rows)}개. 모두 공식 공개 경로(공공데이터포털 파일/API, 기관 공개 게시물, KIPRIS Plus 벌크)에서 받았다. 스크래핑 없음.", "",
          "## 한눈에", "",
          "| 구분 | 건수 |", "|---|---:|",
          *[f"| 기록 종류: {kind_label.get(k, k)} | {v:,} |" for k, v in sorted(kinds.items(), key=lambda x: -x[1])],
          *[f"| 대회 대상자: {a} | {v:,} |" for a, v in sorted(audience.items(), key=lambda x: -x[1])],
          "", "제외 후보 이유(걸러내지 않음, 받는 쪽이 고른다):", "",
          "| 이유 | 뜻 | 건수 |", "|---|---|---:|",
          *[f"| `{c}` | {l} | {n:,} |" for c, l, n in reasons],
          "", "## 외부 공유 보류 소스", "",
          "라이선스에 '보류'가 박힌 소스. xlsx 내보내기 기본값에서 빠지고 `--include-held` 로만 들어간다.", "",
          "| 소스 | 건수 | 라이선스 |", "|---|---:|---|",
          *[f"| {r[1]} | {r[6]:,} | {r[2]} |" for r in held],
          "", "## 소스별 상세", "",
          "| 소스 id | 이름 | 기록 종류 | 건수 | 연도 | 본문 | 처음 받은 날 | 마지막 | 출처 | 라이선스 | 어떻게 |",
          "|---|---|---|---:|---|---:|---|---|---|---|---|"]
    for r in rows:
        sid, name, lic, url, kind, _ex, n, y0, y1, body, first, last = r
        years = f"{y0}~{y1}" if y0 else "—"
        md.append(f"| `{sid}` | {name} | {kind_label.get(kind, kind)} | {n:,} | {years} | {body:,} | {first or ''} | {last or ''} "
                  f"| {url or ''} | {lic} | {how(sid)} |")
    md += ["", "## 받지 않은 것 (조사만)", "",
           "- KIPRIS Plus 아이디어 DB API 38,563건: 1965~2014 학생 대회 98%, 벌크와 84% 중복 → 미적재. `docs/API_KEYS.md`",
           "- 서울 열린데이터 5종(참여예산 28,811 등)·경기 참여예산 4,138·권익위 공개제안(연 1.2~1.8만): 키 확인 완료, 적재는 결정 대기. `docs/API_KEYS.md`",
           "- 공공데이터포털 전체 카탈로그 8,142행 스캔 결과와 143개 후보: `docs/SOURCES.md`",
           "- 성인 창업 공모(K-스타트업 왕중왕전·관광벤처 등)는 데이터셋이 없고 기관 페이지 표·보도자료만: `docs/REVIVAL_SOURCES.md`", ""]
    out.write_text("\n".join(md), encoding="utf-8")
    return {"path": str(out), "sources": len(rows), "ideas": total}
