"""확실한 제외 사유(본문 내용 규칙) + AI 판정 사유. 저장 없음: bluebird master reasons 때 계산.

- 내용 글자 수 = 섹션 라벨 '[..]'·공백·기호 제외
- no_body: 본문 내용 0자 · attachment_only: 라벨·첨부 참조 문구 빼면 0자 · title_repeat: 제목 빼면 0자
- short_title_body: 제목 5자 이하 + 본문 10자 이하(사용자 확정값)
- master.label(AI 판정)이 'idea' 아니면 그 값이 사유 코드, idea인데 근거 확인 안 됨(verified 거짓) = unverified
- 결과: exclude_reasons = '{}' 하나로 사용 대상
"""

from __future__ import annotations

import re

_LABEL = re.compile(r"\[[^\[\]]{1,15}\]")
_NONCONTENT = re.compile(r"[\s\W_]+")
_ATTACH = re.compile(r"(첨부|별첨|붙임)\s*(파일|자료|문서)?\s*(을|를)?\s*(참조|참고|확인)?\s*"
                     r"(해\s*주십시오|하여\s*주십시오|해\s*주세요|바랍니다|합니다|드립니다|하세요)?")

SHORT_TITLE, SHORT_BODY = 5, 10   # 확정 기준(2026-10-20): 제목 5자 이하 + 본문 10자 이하 = 제외
RULE_CODES = ("no_body", "attachment_only", "title_repeat", "short_title_body")
IDEA_CODES = ("idea_thin", "complaint", "abusive", "off_topic", "unverified")


def content(text: str | None) -> str:
    return _NONCONTENT.sub("", _LABEL.sub(" ", text or ""))


def reasons(title: str | None, body: str | None, label: str | None = None, verified: bool | None = None) -> list[str]:
    """제목·본문(+AI 판정·근거 확인) → 사유 코드. 본문 없음이면 다른 본문 조건은 안 붙임."""
    t, b = content(title), content(body)
    if not b:
        return ["no_body"]
    out = []
    if not content(_ATTACH.sub(" ", _LABEL.sub(" ", body or ""))):
        out.append("attachment_only")
    if t and not b.replace(t, ""):
        out.append("title_repeat")
    if len(t) <= SHORT_TITLE and len(b) <= SHORT_BODY:
        out.append("short_title_body")
    if label and label != "idea":
        out.append(label)
    elif label == "idea" and verified is False:
        out.append("unverified")
    return out


def refresh(cur) -> dict[str, int]:
    """master.exclude_reasons의 품질·AI 사유 교체. duplicate는 건드리지 않음."""
    rows = cur.execute("SELECT api, key, title, body, label, verified FROM master").fetchall()
    cur.execute("CREATE TEMP TABLE qn (api text, key text, codes text[], PRIMARY KEY (api, key)) ON COMMIT DROP")
    counts: dict[str, int] = {c: 0 for c in (*RULE_CODES, *IDEA_CODES)}
    with cur.copy("COPY qn FROM STDIN") as cp:
        for api, key, title, body, label, verified in rows:
            codes = reasons(title, body, label, verified)
            for c in codes:
                counts[c] += 1
            cp.write_row((api, key, codes))
    # 바뀐 행만 씀(전체 재기록 = 큰 WAL)
    cur.execute("UPDATE master m SET exclude_reasons = n.reasons FROM"
                " (SELECT q.api, q.key, ARRAY(SELECT x FROM unnest(o.exclude_reasons) x WHERE NOT x = ANY(%s))"
                "  || q.codes AS reasons FROM qn q JOIN master o USING (api, key)) n"
                " WHERE m.api = n.api AND m.key = n.key AND m.exclude_reasons IS DISTINCT FROM n.reasons",
                (list(counts),))
    return counts
