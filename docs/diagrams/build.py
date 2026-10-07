"""파랑새 시스템 구성도 → architecture.html + architecture.pdf

로컬 데모(내 PC · Docker) 구성도. 문구·좌표를 고친 뒤 `python3 docs/diagrams/build.py`.
"""
import subprocess
from html import escape
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "architecture.html"
PDF = HERE / "architecture.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
W, H = 1600, 880

ZONE_STROKE = "#34508a"
ZONE_LABEL = "#d0312d"
FILL_ZONE = "#eef1f8"
GRAY = "#6b7280"
STEP = "#1f8a4c"
NEW = "#2e5aa8"

# Tabler Icons (MIT)
ICONS = {
    "laptop": '<path d="M3 19l18 0"/><path d="M5 7a1 1 0 0 1 1 -1h12a1 1 0 0 1 1 1v8a1 1 0 0 1 -1 1h-12a1 1 0 0 1 -1 -1l0 -8"/>',
    "user": '<path d="M8 7a4 4 0 1 0 8 0a4 4 0 0 0 -8 0"/><path d="M6 21v-2a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4v2"/>',
    "server": '<path d="M3 7a3 3 0 0 1 3 -3h12a3 3 0 0 1 3 3v2a3 3 0 0 1 -3 3h-12a3 3 0 0 1 -3 -3"/><path d="M3 15a3 3 0 0 1 3 -3h12a3 3 0 0 1 3 3v2a3 3 0 0 1 -3 3h-12a3 3 0 0 1 -3 -3l0 -2"/><path d="M7 8l0 .01"/><path d="M7 16l0 .01"/>',
    "database": '<path d="M4 6a8 3 0 1 0 16 0a8 3 0 1 0 -16 0"/><path d="M4 6v6a8 3 0 0 0 16 0v-6"/><path d="M4 12v6a8 3 0 0 0 16 0v-6"/>',
    "shield": '<path d="M12 3a12 12 0 0 0 8.5 3a12 12 0 0 1 -8.5 15a12 12 0 0 1 -8.5 -15a12 12 0 0 0 8.5 -3"/>',
    "internet": '<path d="M3 12a9 9 0 1 0 18 0a9 9 0 0 0 -18 0"/><path d="M3.6 9h16.8"/><path d="M3.6 15h16.8"/><path d="M11.5 3a17 17 0 0 0 0 18"/><path d="M12.5 3a17 17 0 0 1 0 18"/>',
}

zones: list[str] = []
lines_: list[str] = []
parts: list[str] = []
top: list[str] = []


def t(x, y, s, size=12, fill="#374151", anchor="start", weight=400):
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}">{escape(s)}</text>')


def icon(name, x, y, size=16, color="#374151"):
    return f'<use href="#i-{name}" x="{x}" y="{y}" width="{size}" height="{size}" color="{color}"/>'


def zone(x, y, w, h, label, fill):
    zones.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="20" fill="{fill}" '
                 f'stroke="{ZONE_STROKE}" stroke-width="1.6" stroke-dasharray="10,6"/>')
    zones.append(t(x + 20, y + 28, label, 14, ZONE_LABEL, weight=600))


def card(x, y, w, h, kind, headers, body):
    """kind: own(우리 구성요소, 파란 테두리) / plain(외부, 회색 테두리)."""
    stroke = f'stroke="{NEW}" stroke-width="1.6"' if kind == "own" else f'stroke="{GRAY}" stroke-width="1"'
    fill = "#ffffff"
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" {stroke} filter="url(#shadow)"/>')
    hy = y + 16
    for ic, title in headers:
        parts.append(f'<rect x="{x + 12}" y="{hy}" width="{w - 24}" height="28" rx="4" fill="#dcdcdc" stroke="#c4c4c4" stroke-width="0.8"/>')
        parts.append(icon(ic, x + 20, hy + 6))
        parts.append(t(x + w // 2 + 8, hy + 19, title, 13, "#111827", "middle", 600))
        hy += 36
    for i, line in enumerate(body):
        parts.append(t(x + w // 2, hy + 20 + i * 20, line, 12, "#4b5563", "middle"))


def arrow(d, color=GRAY, both=False, dashed=False):
    mk = "a-new" if color == NEW else "a"
    start = f' marker-start="url(#{mk}-s)"' if both else ""
    dash = ' stroke-dasharray="5,4"' if dashed else ""
    lines_.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.6"{dash}{start} marker-end="url(#{mk})"/>')


def label(x, y, s, anchor="middle", color="#111827", bg="#ffffff"):
    w = sum(12 if ord(c) > 0x2000 else 7 for c in s) + 8
    rx = {"middle": x - w // 2, "start": x - 4, "end": x - w + 4}[anchor]
    top.append(f'<rect x="{rx}" y="{y - 13}" width="{w}" height="18" rx="3" fill="{bg}"/>')
    top.append(t(x, y, s, 12, color, anchor, 500))


def step(cx, cy, n, text=None, side="above", color=STEP, bg="#ffffff"):
    top.append(f'<circle cx="{cx}" cy="{cy}" r="10" fill="{color}"/>')
    top.append(t(cx, cy + 4, str(n), 11, "#ffffff", "middle", 700))
    if text and side == "above":
        label(cx, cy - 20, text, "middle", color, bg)
    elif text and side == "right":
        label(cx + 18, cy + 4, text, "start", color, bg)


def note(x, y, w, h, title, body, numbered=False):
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#ffffff" stroke="#9ca3af" stroke-width="1"/>')
    parts.append(t(x + 16, y + 28, title, 13, "#111827", weight=600))
    for i, line in enumerate(body):
        yy = y + 56 + i * 22
        if numbered:
            top.append(f'<circle cx="{x + 26}" cy="{yy - 4}" r="9" fill="{STEP}"/>')
            top.append(t(x + 26, yy, str(i + 1), 10, "#ffffff", "middle", 700))
            parts.append(t(x + 44, yy, line, 12))
        else:
            parts.append(t(x + 16, yy, "- " + line, 12))


# ---------------- 틀 ----------------
zone(32, 96, 1536, 500, "내 PC (Docker)", FILL_ZONE)
zone(860, 130, 300, 430, "PostgreSQL (한 개)", "#ffffff")

# ---------------- 브라우저 ----------------
parts.append(icon("laptop", 70, 150, 48, "#1f2937"))
parts.append(t(94, 222, "브라우저", 14, "#111827", "middle", 600))
parts.append(t(94, 240, "(시민)", 11, GRAY, "middle"))
parts.append(icon("user", 70, 396, 48, "#1f2937"))
parts.append(t(94, 468, "브라우저", 14, "#111827", "middle", 600))
parts.append(t(94, 486, "(관리자)", 11, GRAY, "middle"))

# ---------------- 구성요소 ----------------
card(240, 130, 260, 88, "own", [("server", "포털 (Next.js)")], ["화면 · 조회 · 이의 접수"])
card(240, 380, 260, 88, "own", [("server", "콘솔 (Next.js)")], ["검토 · 승인 · 이의 처리"])
card(560, 380, 240, 88, "own", [("server", "백엔드 API (FastAPI)")], ["토큰 확인 · 역할별 권한"])
card(876, 180, 268, 96, "own", [("database", "공개 DB")], ["승인된 자료 · 이의 접수함"])
card(876, 420, 268, 96, "own", [("database", "원본 DB")], ["아이디어 · 진단 카드 · 근거 URL"])
card(1370, 250, 180, 190, "own", [("server", "처리 작업")], ["적재 · 카드 · 판정", "공개 · 이의 가져오기"])
card(900, 650, 650, 130, "plain", [("internet", "외부 공공 · 상용 API")],
     ["공공데이터포털 · 법제처 · KIPRIS", "네이버 · K-Startup · LLM", "접속 키는 .env 파일에 보관"])

# ---------------- 흐름 ----------------
arrow("M 150,178 H 236", NEW)                       # ① 시민 → 포털
step(193, 178, 1)
arrow("M 500,200 H 872", NEW, both=True)            # ② 포털 ↔ 공개 DB
step(580, 200, 2)
label(730, 190, "읽기 · 이의 접수", "middle", NEW, FILL_ZONE)
arrow("M 150,424 H 236", NEW)                       # ⑤ 관리자 → 콘솔
step(193, 424, 5)
arrow("M 500,424 H 556", NEW)                       # 콘솔 → API
arrow("M 804,448 H 872", GRAY, both=True)           # API ↔ 원본 DB
arrow("M 1366,430 H 1148", GRAY, both=True)         # 처리 작업 ↔ 원본 DB
label(1257, 412, "읽기 · 쓰기", "middle", "#374151", FILL_ZONE)
arrow("M 1366,270 H 1148", GRAY, both=True)         # ④ 처리 작업 → 공개 DB
step(1257, 270, 4)
label(1257, 252, "승인분 반영 · 이의 가져오기", "middle", "#374151", FILL_ZONE)
arrow("M 1460,440 V 646", GRAY)                     # ③ 처리 작업 → 외부 API
step(1460, 540, 3)
label(1448, 506, "허용 목록 · 기록", "end", "#374151", FILL_ZONE)

# ---------------- 설명 ----------------
note(32, 626, 800, 190, "<처리 흐름>", [
    "시민은 브라우저로 포털을 보고 이의를 냅니다.",
    "포털은 공개 DB만 읽습니다. 원본 DB는 볼 수 없습니다.",
    "처리 작업이 외부 API에서 자료를 모아 원본 DB에 저장합니다.",
    "담당자가 승인한 것만 공개 DB로 옮기고, 이의를 가져옵니다.",
    "관리자는 콘솔에서 검토 · 승인합니다. 콘솔은 API만 부릅니다.",
], numbered=True)

symbols = "\n".join(
    f'<symbol id="i-{k}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" '
    f'stroke-linecap="round" stroke-linejoin="round">{v}</symbol>' for k, v in ICONS.items())


def marker(mid, color):
    return (f'<marker id="{mid}" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">'
            f'<polygon points="0 0, 8 3, 0 6" fill="{color}"/></marker>'
            f'<marker id="{mid}-s" markerWidth="8" markerHeight="6" refX="1" refY="3" orient="auto">'
            f'<polygon points="8 0, 0 3, 8 6" fill="{color}"/></marker>')


svg = f"""<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="bb-title bb-desc" font-family="'Pretendard', 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif">
<title id="bb-title">파랑새 시스템 구성도</title>
<desc id="bb-desc">내 PC의 Docker 안에서 모두 돌아간다. 시민은 브라우저로 포털을 보고, 포털은 PostgreSQL의 공개 DB만 읽으며 이의를 접수함에 넣는다. 관리자는 브라우저로 콘솔에 접속하고, 콘솔은 백엔드 API만 부르며 API는 원본 DB를 쓴다. 처리 작업은 허용 목록에 있는 외부 공공·상용 API(공공데이터포털, 법제처, KIPRIS, 네이버, K-Startup, LLM)에서 자료를 모아 원본 DB에 저장하고, 승인된 자료만 공개 DB로 옮기며 이의를 가져온다. 외부 API 키는 .env 파일에 둔다.</desc>
<defs>
<filter id="shadow" x="-10%" y="-10%" width="120%" height="130%"><feDropShadow dx="0" dy="1" stdDeviation="2" flood-color="#000" flood-opacity="0.16"/></filter>
{marker("a", GRAY)}{marker("a-new", NEW)}
{symbols}
</defs>
<rect width="100%" height="100%" fill="#ffffff"/>
{t(32, 60, "파랑새 시스템 구성도", 26, "#111827", weight=600)}
{"".join(zones)}
{"".join(lines_)}
{"".join(parts)}
{"".join(top)}
</svg>"""

OUT.write_text(f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>파랑새 시스템 구성도</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  @page {{ size: {W + 48}px {H + 48}px; margin: 0; }}
  body {{ margin: 0; background: #ffffff; display: flex; justify-content: center; padding: 24px; }}
  svg {{ width: 100%; max-width: {W}px; min-width: 1100px; display: block; }}
  @media print {{ svg {{ width: {W}px; }} }}
</style>
</head>
<body>
{svg}
</body>
</html>
""", encoding="utf-8")

subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=5000",
                f"--print-to-pdf={PDF}", OUT.as_uri()], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
print(f"wrote {OUT.name}, {PDF.name}")
