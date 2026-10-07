"""공공데이터포털에서 공모전·아이디어 수상작 파일데이터를 찾아 메타데이터를 표로 뽑는다.

사용: uv run python tools/opendata_scan.py > ../data/opendata/candidates.tsv
결과 열: id, 제목, 행 수, 확장자, 이용허락범위, atchFileId, fileDetailSn
"""
from __future__ import annotations

import html
import re
import sys
import time
import urllib.parse
import urllib.request

KEYWORDS = ["수상작", "공모전", "아이디어", "경진대회", "창업경진대회", "발명", "국민제안", "제안 공모", "아이디어 공모"]
PAGES = 5
UA = {"User-Agent": "Mozilla/5.0 bluebird-scan"}


def get(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def search(keyword: str, page: int) -> set[str]:
    q = urllib.parse.urlencode({"keyword": keyword, "currentPage": page, "dType": "FILE"})
    return set(re.findall(r"data/(\d+)/fileData\.do", get(f"https://www.data.go.kr/tcs/dss/selectDataSetList.do?{q}")))


def meta(ds_id: str) -> list[str]:
    t = get(f"https://www.data.go.kr/data/{ds_id}/fileData.do")
    title = re.search(r'og:title" content="([^"]+)', t)
    atch = re.search(r"atchFileId=(FILE_\d+)&fileDetailSn=(\d+)", t)
    x = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", t, flags=re.S)))
    x = re.sub(r"\s+", " ", x)
    rows = re.search(r"전체 행 (\d+)", x)
    ext = re.search(r"확장자 (\S+)", x)
    lic = re.search(r"이용허락범위 (.{0,30}?) (?:추천|관련|목록)", x)
    return [ds_id, title.group(1) if title else "", rows.group(1) if rows else "", ext.group(1) if ext else "",
            lic.group(1).strip() if lic else "", atch.group(1) if atch else "", atch.group(2) if atch else ""]


def main() -> None:
    ids: set[str] = set()
    for kw in KEYWORDS:
        for p in range(1, PAGES + 1):
            found = search(kw, p)
            if not found:
                break
            ids |= found
            time.sleep(0.3)
    print("id\ttitle\trows\text\tlicense\tatchFileId\tfileDetailSn")
    for ds_id in sorted(ids):
        try:
            print("\t".join(meta(ds_id)), flush=True)
        except Exception as e:  # noqa: BLE001 — 스캔 도구: 실패한 항목만 표시하고 계속
            print(f"{ds_id}\tERROR {e}", file=sys.stderr)
        time.sleep(0.3)


if __name__ == "__main__":
    main()
