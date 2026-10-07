"""파랑새 시스템 구성도 → architecture.html + architecture.pdf

참고 양식: 연구동행시스템 구성도(붙임2). 문구·좌표를 고친 뒤 `python3 docs/diagrams/build.py`.
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
FILL_INT = "#fdf1ea"
FILL_LINK = "#f3f4f6"
GRAY = "#6b7280"
STEP = "#1f8a4c"
NEW = "#2e5aa8"
OLD = "#9ca3af"

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


def tag(x, y, kind):
    color, text = {"new": (NEW, "신규"), "old": (OLD, "기존")}[kind]
    parts.append(f'<rect x="{x}" y="{y}" width="40" height="18" rx="9" fill="{color}"/>')
    parts.append(t(x + 20, y + 13, text, 11, "#ffffff", "middle", 600))


def card(x, y, w, h, kind, headers, body):
    """kind: new(신규) / old(기존) / plain(태그 없음)."""
    stroke = f'stroke="{NEW}" stroke-width="1.6"' if kind == "new" else f'stroke="{OLD}" stroke-width="1"'
    fill = "#f3f4f6" if kind == "old" else "#ffffff"
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" {stroke} filter="url(#shadow)"/>')
    hy = y + 16
    for ic, title in headers:
        parts.append(f'<rect x="{x + 12}" y="{hy}" width="{w - 24}" height="28" rx="4" fill="#dcdcdc" stroke="#c4c4c4" stroke-width="0.8"/>')
        parts.append(icon(ic, x + 20, hy + 6))
        parts.append(t(x + w // 2 + 8, hy + 19, title, 13, "#111827", "middle", 600))
        hy += 36
    for i, line in enumerate(body):
        parts.append(t(x + w // 2, hy + 20 + i * 20, line, 12, "#4b5563", "middle"))
    if kind in ("new", "old"):
        tag(x - 8, y - 10, kind)


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


def subnet(x, y, w, h, text):
    """업무망 안쪽의 별도 구간(콘솔망·관리망). 점선 파란 상자."""
    zones.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="none" '
                 f'stroke="{NEW}" stroke-width="1.2" stroke-dasharray="6,4"/>')
    zones.append(t(x + 16, y + 20, text, 12, NEW, weight=600))


# ---------------- 구역 ----------------
zone(32, 96, 144, 392, "사용자 Zone", FILL_ZONE)
zone(208, 96, 384, 392, "DMZ Zone (서비스)", FILL_ZONE)
zone(640, 96, 928, 480, "내부 서버 (업무망)", FILL_INT)
zone(640, 616, 352, 192, "DMZ Zone (외부 연계)", FILL_LINK)
zone(1040, 616, 528, 192, "외부 Zone", FILL_ZONE)
subnet(1024, 108, 528, 168, "콘솔망 (콘솔 · API만 연결, 외부 연결 없음)")
subnet(1328, 316, 224, 150, "관리망")

# ---------------- 사용자 ----------------
parts.append(icon("laptop", 80, 160, 48, "#1f2937"))
parts.append(t(104, 232, "국민", 14, "#111827", "middle", 600))
parts.append(t(104, 250, "(일반 이용자)", 11, GRAY, "middle"))

# ---------------- DMZ (서비스) ----------------
card(256, 136, 288, 88, "new", [("server", "Nginx (WAF 뒤)")], ["SSL 암호화 · 요청 검사"])
card(256, 256, 288, 88, "new", [("server", "포털 (Next.js)")], ["화면 · 조회 · 이의 접수"])
card(256, 384, 288, 88, "new", [("database", "공개용 DB")], ["승인된 자료 · 이의 접수함"])

# ---------------- 내부 서버 ----------------
card(688, 128, 272, 136, "plain", [("shield", "공개 · 반출 정책")],
     ["담당자 승인 전에는 비공개", "팀명 · 개인정보 삭제", "외부 AI에는 반출 허용 자료만"])
card(688, 320, 272, 128, "new", [("server", "백엔드 작업 (Python)")], ["수집 · AI 진단 · 점수 · 깔때기", "공개본 밀어넣기 · 이의 가져오기"])
card(1040, 144, 256, 120, "new", [("server", "백엔드 API (FastAPI)")], ["토큰 확인 · 역할별 권한", "내부 DB만 사용"])
card(1344, 144, 192, 120, "new", [("server", "관리자 콘솔")], ["검토 · 승인 · 2인 코딩", "이의 처리"])
card(1040, 320, 256, 128, "new", [("database", "내부 DB (PostgreSQL)")], ["아이디어 · 진단 카드", "근거 URL · 승인 이력"])
parts.append(icon("user", 1416, 350, 48, "#1f2937"))
parts.append(t(1440, 416, "관리자 PC", 14, "#111827", "middle", 600))
parts.append(t(1440, 434, "(업무망 내부)", 11, GRAY, "middle"))

# ---------------- DMZ (외부 연계) · 외부 ----------------
card(672, 664, 288, 112, "new", [("shield", "DMZ 포워드 프록시")], ["허용 도메인만 · 모든 호출 기록"])
card(1072, 664, 464, 112, "plain", [("internet", "외부 API")],
     ["공공데이터포털 · 법제처 · KIPRIS 등", "OpenAI · Anthropic (허용 자료만)"])

# ---------------- 흐름 ----------------
arrow("M 140,180 H 252", NEW)                       # ① 국민 → WAF → Nginx
step(196, 180, 1)
label(196, 160, "HTTPS · WAF", "middle", "#374151", FILL_ZONE)
arrow("M 400,224 V 252", NEW)
label(412, 243, "요청 전달", "start", NEW, FILL_ZONE)
arrow("M 400,344 V 380", NEW, both=True)            # ② 포털 ↔ 공개용 DB
step(400, 362, 2, "조회 · 이의 접수 (DMZ 안)", "right", bg=FILL_ZONE)
arrow("M 684,392 H 548")                            # ③ 업무망 → 공개용 DB (밀어넣기)
step(616, 392, 3, "공개본 밀어넣기", bg=FILL_ZONE)
arrow("M 548,444 H 684")                            # ④ 업무망이 연결해 이의를 가져오고 삭제
step(616, 444, 4, "이의 가져오기·삭제", bg=FILL_ZONE)
label(656, 480, "연결은 항상 업무망이 연다", "start", "#374151", FILL_INT)
lines_.append(f'<line x1="824" y1="264" x2="824" y2="320" stroke="{GRAY}" stroke-width="1.2" stroke-dasharray="2,3"/>')
arrow("M 964,384 H 1036", GRAY, both=True)          # 작업 ↔ 내부 DB
label(1000, 368, "저장 · 조회", "middle", "#374151", FILL_INT)
arrow("M 1168,264 V 316", GRAY, both=True)          # API ↔ 내부 DB
arrow("M 1340,204 H 1300", NEW)                     # 콘솔 → API
arrow("M 880,452 V 660", GRAY, both=True)           # ⑤ 작업 ↔ 프록시
step(880, 528, 5, "외부 조회 (수집 · AI 분석)", "right", bg=FILL_INT)
arrow("M 964,720 H 1068", GRAY, both=True)          # 프록시 ↔ 외부 API
arrow("M 1440,346 V 268", NEW)                      # ⑥ 관리자 PC → 콘솔
step(1440, 300, 6, "콘솔 접속", "right", bg=FILL_INT)

# ---------------- 설명 ----------------
note(32, 512, 560, 138, "<DMZ Zone>", [
    "국민 요청은 DMZ 안에서 끝남 (업무망으로 들어오지 않음)",
    "포털은 공개용 DB만 읽고, 이의 제기는 접수함에만 넣음",
    "업무망으로 들어오는 연결은 0 — 연결은 항상 업무망이 엶",
    "DMZ에서 업무망으로 거는 연결은 모두 차단",
])
note(32, 666, 560, 180, "<처리 흐름>", [
    "국민이 WAF를 거쳐 Nginx로 접속 (HTTPS)",
    "포털은 DMZ의 공개용 DB만 조회 · 이의 접수",
    "승인된 자료를 업무망이 공개용 DB로 밀어넣음 (한 방향)",
    "업무망이 접수함의 이의를 가져오고 DMZ에서 삭제",
    "외부 조회 · AI 분석은 업무망 → DMZ 포워드 프록시",
    "관리자 PC는 관리망에서 콘솔망의 콘솔로만 접속",
], numbered=True)

# 범례
tag(1496, 44, "new"); parts.append(t(1544, 57, "신규", 12))

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
<desc id="bb-desc">국민은 HTTPS로 기관 홈페이지의 파랑새 메뉴에 접속하고, DMZ의 Nginx는 같은 DMZ의 공개용 DB만 조회하므로 국민 요청은 DMZ 안에서 끝난다. 내부 서버의 Backend는 관리자가 승인한 자료만 공개용 DB로 한 방향 반영한다. 자료 수집과 AI 분석은 DMZ 포워드 프록시를 거쳐 외부 API를 조회한다. 관리자는 내부 PC에서 검토하고 승인한다.</desc>
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
