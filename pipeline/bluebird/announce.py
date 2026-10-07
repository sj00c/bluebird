"""공고(C) 신호 — K-Startup 사업공고 15125364만 쓴다(계획 §3.4).

- 키(DATA_GO_KR_KEY)가 있으면 API로 최근 공고를 적재한다(egress 경유, fields_sent=[]: 아이디어 내용 없음).
- 키가 없으면 사람이 실제 공고 URL과 제목·기간을 넣는다(G7 대체 경로). K-Startup URL은 egress로 열어 확인한다.
응답 필드: biz_pbanc_nm(공고명), pbanc_ntrp_nm(공고 기관), pbanc_rcpt_bgng_dt/pbanc_rcpt_end_dt(YYYYMMDD),
detl_pg_url(상세 URL), pbanc_sn(공고번호), aply_trgt_ctnt(신청 대상 내용). 키 도착 후 첫 응답으로 재확인한다.
"""

from __future__ import annotations

import os
from datetime import date

from . import db, wording
from .egress import Egress
from .signals.catalog import today_kst

KSTARTUP_URL = "https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01"


def _ymd(s: object) -> date | None:
    s = str(s or "").strip()[:8]
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:8])) if len(s) == 8 and s.isdigit() else None
    except ValueError:
        return None


def parse_kstartup(payload: dict) -> list[dict]:
    out = []
    for it in payload.get("data") or []:
        url, title = (it.get("detl_pg_url") or "").strip(), (it.get("biz_pbanc_nm") or "").strip()
        sn = str(it.get("pbanc_sn") or "").strip()
        if not (url.startswith(("http://", "https://")) and title and sn):
            continue
        out.append({
            "id": f"kstartup:{sn}", "source": "kstartup", "title": title[:300],
            "summary": (it.get("aply_trgt_ctnt") or it.get("pbanc_ctnt") or "").strip()[:2000] or None,
            "org": (it.get("pbanc_ntrp_nm") or "").strip() or None,
            "apply_from": _ymd(it.get("pbanc_rcpt_bgng_dt")), "apply_to": _ymd(it.get("pbanc_rcpt_end_dt")),
            "url": url,
        })
    return out


def _upsert(conn, a: dict, origin: str, by: str | None) -> None:
    conn.execute(
        """INSERT INTO core.announcement (id, source, title, summary, org, apply_from, apply_to, url)
           VALUES (%(id)s,%(source)s,%(title)s,%(summary)s,%(org)s,%(apply_from)s,%(apply_to)s,%(url)s)
           ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title, summary=EXCLUDED.summary, org=EXCLUDED.org,
             apply_from=EXCLUDED.apply_from, apply_to=EXCLUDED.apply_to, url=EXCLUDED.url, loaded_at=now()""", a)
    conn.execute(
        """INSERT INTO core.condition_change (id, kind, ref_id, occurred_at, url, title, origin, added_by)
           VALUES (%s,'announcement',%s,%s,%s,%s,%s,%s)
           ON CONFLICT (kind, ref_id) DO UPDATE SET title=EXCLUDED.title, url=EXCLUDED.url""",
        (f"announcement:{a['id']}", a["id"], a["apply_from"] or today_kst(), a["url"], a["title"], origin, by))


def fetch(*, dsn: str, pages: int = 3, per_page: int = 100, egress: Egress | None = None) -> dict:
    key = os.environ.get("DATA_GO_KR_KEY")
    if not key:
        raise RuntimeError("DATA_GO_KR_KEY not set: K-Startup은 key_required — `bluebird announce add`로 사람이 공고를 넣는다")
    own = egress is None
    eg = egress or Egress.from_dsn(dsn)
    n = 0
    try:
        with db.pipeline_run(dsn, "announce") as stats, db.connect(dsn) as conn:
            for page in range(1, pages + 1):
                r = eg.get("collect", KSTARTUP_URL,
                           params={"page": page, "perPage": per_page, "returnType": "json"},
                           path_template="/B552735/kisedKstartupService01/getAnnouncementInformation01",
                           secret_params={"serviceKey": key})
                if r.status != 200:
                    raise RuntimeError(f"K-Startup HTTP {r.status}")
                items = parse_kstartup(r.json())
                for a in items:
                    _upsert(conn, a, "api", None)
                n += len(items)
                if len(items) < per_page:
                    break
            conn.commit()
            stats["announcements"] = n
    finally:
        if own:
            eg.close()
    print(f"[announce] K-Startup {n}")
    return {"announcements": n}


def add(*, dsn: str, url: str, title: str, org: str | None, apply_from: date | None, apply_to: date | None,
        summary: str | None, by: str, egress: Egress | None = None) -> str:
    """사람이 실제 K-Startup 공고를 넣는다. URL은 k-startup.go.kr이어야 하고 egress로 열어 200을 확인한다."""
    if "k-startup.go.kr" not in url.split("/")[2]:
        raise ValueError("공고 소스는 K-Startup만 쓴다(k-startup.go.kr URL)")
    wording.check(title, summary)
    if egress is not None:
        r = egress.get("collect", url, path_template="/web/contents/bizpbanc")
        if r.status != 200:
            raise ValueError(f"{url} returned HTTP {r.status}")
    sn = url.rstrip("/").split("pbancSn=")[-1].split("&")[0] if "pbancSn=" in url else url
    a = {"id": f"kstartup:{sn}", "source": "manual", "title": title, "summary": summary, "org": org,
         "apply_from": apply_from, "apply_to": apply_to, "url": url}
    with db.connect(dsn) as conn:
        _upsert(conn, a, "human", by)
        conn.commit()
    return a["id"]
