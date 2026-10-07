"""`bluebird sources check` — 어떤 데이터가 실제로 불러와지는지 반복 점검(계획 §4, G13).

- 파일 소스: seed 파일 존재·sha256·행 수·첫 행 표본(마스킹 후)·라이선스.
- 외부 소스: egress(→ 프록시)로 실제 호출. 키가 없으면 키 없이 불러 401 등 "키 필요" 응답을 확인하고 key_required로,
  키 환경변수가 있으면 키를 붙여 불러 ok/error로 기록한다. 키 도착 시 같은 명령을 다시 돌리면 된다.
- 결과는 core.source_check에 1행씩 남고 표로 출력된다. 아이디어 내용은 어떤 점검 호출에도 넣지 않는다.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from psycopg.types.json import Jsonb

from . import db
from .egress import Egress, EgressBlocked, Response
from .ingest import load_secret
from .sources import ADAPTERS, file_sha256, load_sources

DATA_GO_KR = "https://apis.data.go.kr"


@dataclass(frozen=True)
class Remote:
    id: str
    role: str           # 원본 | 바뀐 것(D/R/C/M) | 흔적 | LLM
    tier: str           # must | stretch
    url: str
    license: str
    key_env: tuple[str, ...] = ()
    refresh: str | None = None
    # 키를 요청에 붙이는 방법: (params, headers)
    auth: Callable[[dict[str, str]], tuple[dict, dict]] = lambda k: ({}, {})
    params: tuple[tuple[str, str], ...] = ()
    # 응답 → (status, rows, sample)
    parse: Callable[[Response, bool], tuple[str, int | None, object]] | None = None


def _needs_key(r: Response) -> bool:
    t = r.text[:2000]
    if r.status in (401, 403):
        return True
    return r.status < 300 and any(s in t for s in (
        "SERVICE_KEY_IS_NULL", "SERVICE KEY IS NOT REGISTERED", "인증키를 입력", "Authentication failed"))


def _json_rows(path: list[str], count_path: list[str] | None = None):
    def parse(r: Response, keyed: bool):
        if r.status >= 400 or _needs_key(r):
            return ("key_required" if _needs_key(r) and not keyed else "error"), None, _err_sample(r, keyed)
        d = r.json()
        node = d
        for k in path:
            node = node.get(k, {}) if isinstance(node, dict) else {}
        items = node if isinstance(node, list) else [node] if node else []
        total = d
        for k in count_path or []:
            total = total.get(k) if isinstance(total, dict) else None
        return "ok", int(total) if isinstance(total, (int, str)) and str(total).isdigit() else len(items), \
            items[0] if items else None
    return parse


def _err_sample(r: Response, keyed: bool) -> object:
    """키 없이 부른 응답은 앞부분을 남긴다(키가 없으니 되돌아올 키도 없다).
    키를 붙인 요청의 오류 응답은 본문을 남기지 않는다 — 공급자가 키 일부를 되돌려 주는 경우가 있다."""
    return {"http_status": r.status} if keyed else r.text[:200]


def _probe_only(r: Response, keyed: bool):
    if _needs_key(r) or r.status >= 400:
        return ("key_required" if _needs_key(r) and not keyed else "error"), None, _err_sample(r, keyed)
    return "ok", None, None if keyed else r.text[:200]


def _kipris(r: Response, keyed: bool):
    if "<successYN>Y" in r.text:
        return "ok", None, r.text[:300]
    return ("key_required" if not keyed else "error"), None, _err_sample(r, keyed)


REMOTES: tuple[Remote, ...] = (
    Remote("datagokr_catalog_15062804", "바뀐 것 D(목록개방현황)", "must",
           "https://www.data.go.kr/tcs/dss/selectFileDataDownload.do", "이용허락범위 제한 없음",
           refresh="월 1회(포털 nextRegistPrarnde)"),
    Remote("law_drf_eflaw", "바뀐 것 R(시행 법령)", "stretch", "https://www.law.go.kr/DRF/lawSearch.do",
           "국가법령정보 공동활용(무료, OC 필요)", key_env=("LAW_OC",),
           auth=lambda k: ({"OC": k.get("LAW_OC") or "test"}, {}),
           params=(("target", "eflaw"), ("type", "JSON"), ("display", "1")),
           parse=_json_rows(["LawSearch", "law"], ["LawSearch", "totalCnt"])),
    Remote("kstartup_announcement_15125364", "공고 매칭(C)", "must",
           f"{DATA_GO_KR}/B552735/kisedKstartupService01/getAnnouncementInformation01", "이용허락범위 제한 없음",
           key_env=("DATA_GO_KR_KEY",), auth=lambda k: ({"serviceKey": k["DATA_GO_KR_KEY"]}, {}),
           params=(("page", "1"), ("perPage", "1"), ("returnType", "json")),
           parse=_json_rows(["data"], ["totalCount"])),
    Remote("acrc_public_proposal_15059115", "원본 확장(국민 제안)", "stretch",
           f"{DATA_GO_KR}/1140100/PublicProposalService2/PublicProposalItem", "이용허락범위 제한 없음",
           key_env=("DATA_GO_KR_KEY",), auth=lambda k: ({"serviceKey": k["DATA_GO_KR_KEY"]}, {}),
           params=(("pageNo", "1"), ("numOfRows", "1"), ("type", "json")), parse=_probe_only),
    Remote("bizinfo_announcement", "공고 매칭(C)", "stretch", "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do",
           "기업마당 Open API(자체 키)", key_env=("BIZINFO_KEY",), auth=lambda k: ({"crtfcKey": k["BIZINFO_KEY"]}, {}),
           params=(("dataType", "json"), ("searchCnt", "1")), parse=_probe_only),
    Remote("naver_search_news", "흔적 news_web", "must", "https://openapi.naver.com/v1/search/news.json",
           "NAVER 검색 API(일 25,000건)", key_env=("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"),
           auth=lambda k: ({}, {"X-Naver-Client-Id": k["NAVER_CLIENT_ID"],
                                "X-Naver-Client-Secret": k["NAVER_CLIENT_SECRET"]}),
           params=(("query", "공공데이터"), ("display", "1")), parse=_json_rows(["items"], ["total"])),
    Remote("kipris_plus_patent", "흔적 ip", "must",
           "https://plus.kipris.or.kr/kipo-api/kipi/patUtiModInfoSearchSevice/getWordSearch",
           "KIPRIS Plus 이용약관(확인 필요)", key_env=("KIPRIS_PLUS_KEY",),
           auth=lambda k: ({"ServiceKey": k["KIPRIS_PLUS_KEY"]}, {}),
           params=(("word", "공공데이터"), ("year", "0"), ("numOfRows", "1")), parse=_kipris),
    Remote("openai_api", "LLM(P1·P2·P3·판정)", "must", "https://api.openai.com/v1/models", "상용 API 약관",
           key_env=("OPENAI_API_KEY",), auth=lambda k: ({}, {"Authorization": f"Bearer {k['OPENAI_API_KEY']}"}),
           parse=_probe_only),
    Remote("anthropic_api", "LLM(P1·P2·P3·판정)", "must", "https://api.anthropic.com/v1/models", "상용 API 약관",
           key_env=("ANTHROPIC_API_KEY",),
           auth=lambda k: ({}, {"x-api-key": k["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"}),
           parse=_probe_only),
)

BLOCKED = (  # 협약 전 범위 밖. 호출하지 않고 상태만 남긴다(계획 §4.3).
    ("modu_idea", "원본(모두의 아이디어, 2.7만 접수)", "공개 목록·API 없음 → 기관 협약 필요"),
    ("gukmin_saenggakham", "원본(국민생각함, 웹 7,438건)", "API 없음 → 협약 필요"),
    ("idearo_ipmarket", "원본(아이디어로)", "API 없음 → 협약 필요"),
)


def _check_catalog(eg: Egress) -> tuple[str, int | None, object, Response]:
    from .signals.catalog import CATALOG_DETAIL_PK, CATALOG_PK
    r = eg.post_form("source_check", "https://www.data.go.kr/tcs/dss/selectFileDataDownload.do",
                     {"publicDataPk": CATALOG_PK, "publicDataDetailPk": CATALOG_DETAIL_PK,
                      "publicDataTyCode": "PR0051"}, path_template="/tcs/dss/selectFileDataDownload.do")
    d = r.json()
    info = d.get("dataSetFileDetailInfo") or {}
    ok = bool(d.get("atchFileId"))
    # 행 수는 다운로드해야 알 수 있다(주간 snapshot.sh). 여기서는 받을 수 있는지와 갱신 주기만 본다.
    sample = {k: info.get(k) for k in ("dataNm", "stdrDe", "updtDt", "nextRegistPrarnde")}
    return ("ok" if ok else "error"), None, sample, r


def check_remote(eg: Egress, rem: Remote) -> dict:
    keys = {k: os.environ.get(k, "") for k in rem.key_env}
    keyed = bool(rem.key_env) and all(keys.values())
    try:
        if rem.id == "datagokr_catalog_15062804":
            status, rows, sample, resp = _check_catalog(eg)
            return {"status": status, "rows": rows, "sample": sample, "http_status": resp.status, "keyed": False,
                    "egress_call_id": resp.egress_call_id,
                    "note": f"기준일 {sample['stdrDe']}, 다음 등록 예정 {sample['nextRegistPrarnde']}"}
        params, headers = rem.auth(keys) if (keyed or rem.id == "law_drf_eflaw") else ({}, {})
        r = eg.get("source_check", rem.url, params=dict(rem.params), path_template="/" + rem.url.split("://", 1)[1].split("/", 1)[1], secret_params=params, secret_headers=headers)
        status, rows, sample = (rem.parse or _probe_only)(r, keyed)
        if rem.id == "law_drf_eflaw" and status == "ok" and not os.environ.get("LAW_OC"):
            status, note = "ok", "OC=test(시험 계정)로 응답. 운영은 OC 발급 필요"
        else:
            note = None
        return {"status": status, "rows": rows, "sample": sample, "http_status": r.status, "keyed": keyed,
                    "egress_call_id": r.egress_call_id, "note": note}
    except EgressBlocked as e:
        return {"status": "blocked", "rows": None, "sample": str(e), "http_status": None, "keyed": keyed, "egress_call_id": None}
    except Exception as e:  # noqa: BLE001 — 네트워크·파싱 오류도 점검 결과로 남긴다
        return {"status": "error", "rows": None, "sample": f"{type(e).__name__}: {e}"[:300], "http_status": None,
                    "keyed": keyed, "egress_call_id": None}


def check_files(config: Path, seed_dir: Path, secret: bytes) -> list[dict]:
    out = []
    for spec in load_sources(config, seed_dir):
        if not spec.path.exists():
            out.append({"source_id": spec.id, "role": "원본", "tier": "must", "status": "error", "rows": None,
                            "sample": f"{spec.path.name} not in seed dir", "license": spec.license})
            continue
        rows = list(ADAPTERS[spec.adapter](spec, secret))
        r0 = rows[0] if rows else {}
        sample = {k: r0.get(k) for k in ("idea_id", "year", "award", "title")}
        sample["body"] = (r0.get("body") or "")[:80] or None
        out.append({"source_id": spec.id, "role": "원본", "tier": "must", "status": "ok", "rows": len(rows), "sample": sample,
                        "license": spec.license, "note": f"sha256 {file_sha256(spec.path)[:12]}, 본문 "
                        f"{sum(1 for r in rows if r['body'])}건, public_ok={spec.public_ok}, "
                        f"export_grade={spec.export_grade}"})
    return out


def run(*, dsn: str, config: Path, seed_dir: Path, secret_path: Path, egress: Egress | None = None) -> list[dict]:
    results = check_files(config, seed_dir, load_secret(secret_path))
    own = egress is None
    eg = egress or Egress.from_dsn(dsn)
    try:
        for rem in REMOTES:
            r = check_remote(eg, rem)
            results.append({"source_id": rem.id, "role": rem.role, "tier": rem.tier, "license": rem.license,
                                "refresh_cadence": rem.refresh, **r})
    finally:
        if own:
            eg.close()
    for sid, role, why in BLOCKED:
        results.append({"source_id": sid, "role": role, "tier": "범위 밖", "status": "blocked", "rows": None, "sample": None,
                            "license": None, "note": why})
    with db.connect(dsn) as conn:
        for r in results:
            conn.execute(
                """INSERT INTO core.source_check (source_id, status, http_status, rows, sample, license,
                     refresh_cadence, note, egress_call_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (r["source_id"], r["status"], r.get("http_status"), r.get("rows"),
                 Jsonb(r.get("sample"), dumps=lambda o: json.dumps(o, ensure_ascii=False, default=str)),
                 r.get("license"), r.get("refresh_cadence"), r.get("note"), r.get("egress_call_id")),
            )
        conn.commit()
    return results


def print_table(results: list[dict], out=sys.stdout) -> None:
    print(f"{'소스':34} {'역할':22} {'구분':7} {'상태':13} {'HTTP':>4} {'행':>8}  비고", file=out)
    for r in results:
        rows = f"{r['rows']:,}" if isinstance(r.get("rows"), int) else "-"
        note = r.get("note") or (json.dumps(r.get("sample"), ensure_ascii=False, default=str)[:70]
                                  if r["status"] != "ok" else "")
        print(f"{r['source_id']:34} {r['role'][:22]:22} {r['tier']:7} {r['status']:13} "
              f"{r.get('http_status') or '-':>4} {rows:>8}  {note}", file=out)
