"""상세 페이지 HTML → 본문 텍스트(표준 라이브러리만)."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser


class _Block(HTMLParser):
    """첫 <tag class="cls"> 요소 안 텍스트. 블록 요소 경계 = 줄바꿈."""
    _BREAK = frozenset({"div", "p", "br", "li", "tr"})

    def __init__(self, tag: str, cls: str):
        super().__init__(convert_charrefs=True)
        self.tag, self.cls, self.depth, self.done, self.parts = tag, cls, 0, False, []

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        if self.depth:
            self.depth += tag == self.tag
            if tag in self._BREAK:
                self.parts.append("\n")
        elif tag == self.tag and self.cls in (dict(attrs).get("class") or "").split():
            self.depth = 1

    def handle_endtag(self, tag):
        if self.depth and tag == self.tag:
            self.depth -= 1
            self.done = self.depth == 0

    def handle_data(self, data):
        if self.depth and not self.done:
            self.parts.append(data)


def block(page: str, tag: str, cls: str) -> str:
    parser = _Block(tag, cls)
    parser.feed(page)
    return "".join(parser.parts).strip()


def th_value(page: str, label: str) -> str:
    """<th>label</th><td>값</td> 의 값 텍스트(태그 제거, <br> = 줄바꿈, 숨김 <label> 제거). 없으면 ""."""
    m = re.search(rf"<th[^>]*>\s*{re.escape(label)}\s*</th>\s*<td[^>]*>(.*?)(?:</td>|</tr>)", page, re.DOTALL)
    if not m:
        return ""
    text = re.sub(r"<label[^>]*>.*?</label>", "", m.group(1), flags=re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def th_sections(page: str, labels: tuple[str, ...]) -> str:
    """여러 칸 → '[라벨] 값' 줄. 빈 칸 생략."""
    return "\n".join(f"[{label}] {v}" for label in labels if (v := th_value(page, label)))
