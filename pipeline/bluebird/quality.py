"""행 품질 측정 + 확실한 제외 사유. 임계값 = 사용자 확정값만(제목 5자 이하 + 본문 10자 이하).

- 내용 글자 수 = 섹션 라벨 '[..]'·공백·기호 제외
- no_body: 본문 내용 0자 · attachment_only: 라벨·첨부 참조 문구 빼면 0자 · title_repeat: 제목 빼면 0자
- short_title_body: 제목 5자 이하 + 본문 10자 이하
- has_profanity·has_repeat·hangul_ratio = 표시만(단어 규칙 오탐 → 제외 조건 아님)
- idea_label(AI 판정)이 'idea' 아니면 그 값이 사유 코드. 판정 칸은 재계산 때 유지
"""

from __future__ import annotations

import re

_LABEL = re.compile(r"\[[^\[\]]{1,15}\]")
_NONCONTENT = re.compile(r"[\s\W_]+")
_ATTACH = re.compile(r"(첨부|별첨|붙임)\s*(파일|자료|문서)?\s*(을|를)?\s*(참조|참고|확인)?\s*"
                     r"(해\s*주십시오|하여\s*주십시오|해\s*주세요|바랍니다|합니다|드립니다|하세요)?")
_PROFANITY = re.compile(r"씨발|시발놈|ㅅㅂ|ㅆㅂ|개새끼|병신|븅신|좆|지랄")
_REPEAT = re.compile(r"ㅋ{4,}|ㅎ{4,}|!{4,}|\?{4,}")
_HANGUL = re.compile(r"[가-힣]")

SHORT_TITLE, SHORT_BODY = 5, 10   # 확정 기준(2026-10-20): 제목 5자 이하 + 본문 10자 이하 = 제외
RULE_CODES = ("no_body", "attachment_only", "title_repeat", "short_title_body")
IDEA_CODES = ("idea_thin", "complaint", "abusive", "off_topic")


def content(text: str | None) -> str:
    return _NONCONTENT.sub("", _LABEL.sub(" ", text or ""))


def measure(title: str | None, body: str | None) -> dict:
    t, b = content(title), content(body)
    return {
        "title_len": len(t),
        "body_len": len(b),
        "hangul_ratio": round(len(_HANGUL.findall(b)) / len(b), 3) if b else None,
        "attachment_only": bool(b) and not content(_ATTACH.sub(" ", _LABEL.sub(" ", body or ""))),
        "title_repeat": bool(b) and bool(t) and not b.replace(t, ""),
        "has_profanity": bool(_PROFANITY.search(body or "")),
        "has_repeat": bool(_REPEAT.search(body or "")),
    }


def reasons(m: dict, idea_label: str | None = None) -> list[str]:
    """측정값(+AI 판정) → 사유 코드. 본문 없음이면 다른 본문 조건은 안 붙임."""
    if m["body_len"] == 0:
        return ["no_body"]
    out = [c for c in ("attachment_only", "title_repeat") if m[c]]
    if m["title_len"] <= SHORT_TITLE and m["body_len"] <= SHORT_BODY:
        out.append("short_title_body")
    if idea_label and idea_label != "idea":
        out.append(idea_label)
    return out


_COLS = ("title_len", "body_len", "hangul_ratio", "attachment_only", "title_repeat", "has_profanity", "has_repeat")


def refresh(cur) -> dict[str, int]:
    """quality 측정값 재계산(idea_* 유지) + master.exclude_reasons의 품질 사유 교체. duplicate는 건드리지 않음."""
    rows = cur.execute("SELECT m.api, m.key, m.title, m.body, q.idea_label FROM master m"
                       " LEFT JOIN quality q USING (api, key)").fetchall()
    cur.execute("CREATE TEMP TABLE qn (api text, key text, title_len int, body_len int, hangul_ratio real,"
                " attachment_only bool, title_repeat bool, has_profanity bool, has_repeat bool, codes text[],"
                " PRIMARY KEY (api, key)) ON COMMIT DROP")
    counts: dict[str, int] = {c: 0 for c in (*RULE_CODES, *IDEA_CODES)}
    with cur.copy("COPY qn FROM STDIN") as cp:
        for api, key, title, body, label in rows:
            m = measure(title, body)
            codes = reasons(m, label)
            for c in codes:
                counts[c] += 1
            cp.write_row((api, key, *(m[c] for c in _COLS), codes))
    cur.execute(f"INSERT INTO quality (api, key, {', '.join(_COLS)}) SELECT api, key, {', '.join(_COLS)} FROM qn"
                f" ON CONFLICT (api, key) DO UPDATE SET {', '.join(f'{c} = EXCLUDED.{c}' for c in _COLS)}")
    cur.execute("UPDATE master m SET exclude_reasons ="
                " ARRAY(SELECT x FROM unnest(m.exclude_reasons) x WHERE NOT x = ANY(%s)) || q.codes"
                " FROM qn q WHERE m.api = q.api AND m.key = q.key", (list(counts),))
    return counts
