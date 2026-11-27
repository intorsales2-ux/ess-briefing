"""계절 장식 — 발행 날짜에 맞춰 마스트헤드 띠와 메일 표지 그림을 자동으로 고른다.

- 달력은 PERIODS 한 곳에서 관리한다(월·일 기준이라 해가 바뀌어도 그대로 돈다).
- 그림은 '같은 에너지 현장의 사계절' — ESS 컨테이너·풍력·태양광이 선 지평선에 계절만 바뀐다.
- 웹 지면: 코드로 그린 SVG를 지면에 직접 넣는다(외부 이미지 요청 없음).
- 메일 표지: docs/assets/season/<테마>.png (미리 만들어 둔 그림)를 쓴다.
- config.yaml 의 season 값으로 끄거나(off) 특정 테마로 고정할 수 있다(기본 auto).
"""
from __future__ import annotations

import math
import random
from datetime import date

# (테마, 시작 (월, 일), 끝 (월, 일)) — 끝이 시작보다 앞이면 해를 넘기는 기간
PERIODS = [
    ("christmas", (11, 25), (12, 25)),
    ("newyear", (12, 26), (1, 10)),
    ("winter", (1, 11), (2, 29)),
    ("spring", (3, 1), (5, 31)),
    ("summer", (6, 1), (8, 31)),
    ("autumn", (9, 1), (11, 24)),
]

THEMES = {
    "christmas": {"ko": "크리스마스", "en": "Merry Christmas", "msg": "따뜻한 연말 보내세요",
                  "sky": ("#0E2A24", "#0B1820"), "glow": None, "hill": "#12332A", "hill2": "#0F2922",
                  "unit": "#1D4034", "edge": "#7FC7A0", "ink": "#F4EFE2", "mail_bg": "#0E2A24"},
    "newyear": {"ko": "새해", "en": "Happy New Year", "msg": "새해 복 많이 받으세요",
                "sky": ("#141B3A", "#2A1B33"), "glow": ("#F2B233", 0.55), "hill": "#231C36", "hill2": "#1B1830",
                "unit": "#2E2748", "edge": "#F2C76B", "ink": "#FFF4D6", "mail_bg": "#141B3A"},
    "winter": {"ko": "겨울", "en": "Winter Season", "msg": "추운 날씨, 건강 유의하세요",
               "sky": ("#132638", "#0E1A26"), "glow": None, "hill": "#1B3247", "hill2": "#16293B",
               "unit": "#24405A", "edge": "#A9CDEB", "ink": "#EAF4FF", "mail_bg": "#132638"},
    "spring": {"ko": "봄", "en": "Hello, Spring", "msg": "새봄, 새 출발을 응원합니다",
               "sky": ("#12302B", "#10221F"), "glow": ("#C8E68C", 0.30), "hill": "#1F4A2C", "hill2": "#193D26",
               "unit": "#285A36", "edge": "#A6DB7C", "ink": "#F3FBE6", "mail_bg": "#12302B"},
    "summer": {"ko": "여름", "en": "Summer Season", "msg": "무더위에 건강 유의하세요",
               "sky": ("#0E2C45", "#0D2030"), "glow": ("#FFD166", 0.42), "hill": "#134458", "hill2": "#103848",
               "unit": "#1A5670", "edge": "#7FD3E8", "ink": "#EAF9FF", "mail_bg": "#0E2C45"},
    "autumn": {"ko": "가을", "en": "Autumn Season", "msg": "풍성한 가을 되세요",
               "sky": ("#1E2233", "#2B1E1C"), "glow": ("#F08A3C", 0.40), "hill": "#3A2A1C", "hill2": "#2E2218",
               "unit": "#4A3421", "edge": "#F0B36B", "ink": "#FFF1DC", "mail_bg": "#1E2233"},
}

W, H, GROUND = 1200, 96, 84


def theme_for(day: date) -> str:
    md = (day.month, day.day)
    for key, start, end in PERIODS:
        if start <= end:
            if start <= md <= end:
                return key
        elif md >= start or md <= end:  # 해를 넘기는 기간
            return key
    return "winter"


def pick(day: date, mode: str = "auto") -> dict | None:
    """발행일의 계절 테마. mode: auto(달력) / off(장식 없음) / 테마 이름(고정)."""
    mode = (mode or "auto").strip().lower()
    if mode in ("off", "none", "false", "0"):
        return None
    key = mode if mode in THEMES else theme_for(day)
    t = dict(THEMES[key])
    t["key"] = key
    t["svg"] = scene_svg(key)
    t["label"] = f'{t["en"]} — {t["msg"]}'
    return t


# ───────────────────────── 그림 조각 ─────────────────────────
def _f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _container(x: float, t: dict, snow: bool) -> str:
    y, w, h = GROUND - 17, 50, 17
    s = (f'<rect x="{_f(x)}" y="{y}" width="{w}" height="{h}" rx="1.2" fill="{t["unit"]}"/>'
         f'<rect x="{_f(x)}" y="{y}" width="{w}" height="1.6" fill="{t["edge"]}" opacity=".55"/>')
    for k in (12.5, 25, 37.5):  # 문짝 이음선
        s += f'<rect x="{_f(x + k - .4)}" y="{y + 3}" width=".8" height="{h - 5}" fill="#000" opacity=".28"/>'
    s += f'<rect x="{_f(x + 4)}" y="{y + 6}" width="5" height="4" rx=".6" fill="{t["edge"]}" opacity=".5"/>'  # 상태 표시창
    if snow:
        s += f'<path d="M{_f(x - 1)} {y + .6} q6 -4.4 12 -2.6 q7 -3.4 14 -1 q8 -3 14 -.2 q6 -1.6 12 3.8 z" fill="#fff" opacity=".92"/>'
    return s


def _turbine(x: float, h: float, ang: float, t: dict) -> str:
    top = GROUND - h
    s = f'<path d="M{_f(x - 1.1)} {GROUND} L{_f(x - .5)} {_f(top)} h1 L{_f(x + 1.1)} {GROUND} z" fill="{t["edge"]}" opacity=".5"/>'
    r = h * 0.36
    for k in range(3):
        a = math.radians(ang + 120 * k)
        s += (f'<line x1="{_f(x)}" y1="{_f(top)}" x2="{_f(x + r * math.cos(a))}" y2="{_f(top + r * math.sin(a))}" '
              f'stroke="{t["edge"]}" stroke-width="1.5" stroke-linecap="round" opacity=".62"/>')
    return s + f'<circle cx="{_f(x)}" cy="{_f(top)}" r="1.7" fill="{t["edge"]}" opacity=".8"/>'


def _panels(x: float, n: int, t: dict) -> str:
    s = ""
    for k in range(n):
        px = x + k * 15
        s += (f'<path d="M{_f(px)} {GROUND} l4 -7 h10 l-4 7 z" fill="{t["edge"]}" opacity=".34"/>'
              f'<path d="M{_f(px + 4)} {GROUND - 7} h10" stroke="{t["edge"]}" stroke-width=".8" opacity=".7"/>')
    return s


def _tree(x: float, h: float, rnd: random.Random, lights: bool) -> str:
    base = GROUND + 1
    s = f'<rect x="{_f(x - 1.2)}" y="{_f(base - 4)}" width="2.4" height="4" fill="#3B2A1C"/>'
    for k, (ww, yy) in enumerate(((h * .46, 0), (h * .36, h * .28), (h * .25, h * .54))):
        ty = base - 3 - yy
        s += f'<path d="M{_f(x - ww)} {_f(ty)} L{_f(x)} {_f(ty - h * .46)} L{_f(x + ww)} {_f(ty)} z" fill="#1F5A40"/>'
        s += f'<path d="M{_f(x - ww * .55)} {_f(ty - h * .2)} q{_f(ww * .55)} -3 {_f(ww * 1.1)} 0" stroke="#fff" stroke-width="1.5" fill="none" opacity=".8" stroke-linecap="round"/>'
        if lights:
            col = ("#E9695F", "#F2B233", "#5B96F5")[k]
            s += f'<circle cx="{_f(x + rnd.uniform(-ww * .5, ww * .5))}" cy="{_f(ty - 3)}" r="1.5" fill="{col}"/>'
    if lights:
        s += f'<path d="M{_f(x)} {_f(base - 3 - h * 1.02)} l1.3 2.7 3 .4 -2.2 2 .6 3 -2.7 -1.5 -2.7 1.5 .6 -3 -2.2 -2 3 -.4 z" fill="#F2B233"/>'
    return s


def _site(t: dict, snow: bool, trees: bool, rnd: random.Random) -> str:
    """지평선 — 언덕, 풍력, 태양광, ESS 컨테이너(계절과 무관하게 같은 현장)."""
    s = (f'<path d="M0 {GROUND - 5} C150 {GROUND - 15} 300 {GROUND - 2} 470 {GROUND - 8} S800 {GROUND - 16} 960 {GROUND - 6} '
         f'S1130 {GROUND - 12} {W} {GROUND - 7} V{H} H0 z" fill="{t["hill2"]}"/>')
    for x, h, a in ((334, 54, 18), (424, 40, 70), (792, 60, 42), (1094, 46, 96), (86, 36, 55)):
        s += _turbine(x, h, a, t)
    s += f'<path d="M0 {GROUND} H{W} V{H} H0 z" fill="{t["hill"]}"/>'
    if snow:
        s += f'<path d="M0 {GROUND} q150 -3 300 0 t300 0 t300 0 t300 0 V{GROUND + 3.2} H0 z" fill="#fff" opacity=".9"/>'
    s += _panels(690, 4, t) + _panels(1010, 3, t) + _panels(232, 3, t)
    for x in (150, 520, 574, 628, 904, 958):
        s += _container(x, t, snow)
    if trees:
        for x, h in ((54, 30), (292, 24), (474, 34), (760, 22), (860, 30), (1150, 34)):
            s += _tree(x, h, rnd, True)
    return s


def _snowfall(rnd: random.Random, n: int, big: bool) -> str:
    s = ""
    for _ in range(n):
        x, y, r = rnd.uniform(0, W), rnd.uniform(4, GROUND - 2), rnd.choice((.8, 1, 1.2, 1.6))
        s += f'<circle cx="{_f(x)}" cy="{_f(y)}" r="{r}" fill="#fff" opacity="{rnd.choice((".45", ".65", ".9"))}"/>'
    if big:  # 눈 결정 몇 개
        for x, y, r in ((392, 26, 7), (702, 18, 5.5), (1012, 30, 6.5), (176, 22, 5)):
            for k in range(3):
                a = math.radians(60 * k)
                dx, dy = r * math.cos(a), r * math.sin(a)
                s += (f'<line x1="{_f(x - dx)}" y1="{_f(y - dy)}" x2="{_f(x + dx)}" y2="{_f(y + dy)}" '
                      f'stroke="#DCEEFF" stroke-width="1.1" stroke-linecap="round" opacity=".8"/>')
    return s


def _lights() -> str:
    """꼬마전구 줄 — 지면 팔레트(빨강·노랑·파랑·초록)."""
    cols = ("#E9695F", "#F2B233", "#5B96F5", "#8CCB63")
    s, k = "", 0
    for x0 in range(0, W, 150):
        s += f'<path d="M{x0} 0 q75 20 150 0" stroke="#0A0F12" stroke-width="1" fill="none" opacity=".75"/>'
        for i in range(1, 6):
            u = i / 6
            x = x0 + 150 * u
            y = 40 * u * (1 - u)  # 처진 줄(2차 곡선)
            c = cols[k % 4]; k += 1
            s += (f'<circle cx="{_f(x)}" cy="{_f(y + 2.6)}" r="5" fill="{c}" opacity=".16"/>'
                  f'<circle cx="{_f(x)}" cy="{_f(y + 2.6)}" r="2.3" fill="{c}"/>')
    return s


def _fireworks(rnd: random.Random) -> str:
    s = ""
    for cx, cy, r, col in ((250, 30, 20, "#F2C76B"), (486, 22, 15, "#F28BA8"), (706, 32, 22, "#8FB8FF"),
                           (930, 22, 16, "#F2C76B"), (1110, 34, 18, "#F28BA8")):
        for k in range(14):
            a = math.radians(360 / 14 * k + rnd.uniform(-5, 5))
            r0, r1 = r * .34, r * rnd.uniform(.82, 1)
            s += (f'<line x1="{_f(cx + r0 * math.cos(a))}" y1="{_f(cy + r0 * math.sin(a))}" x2="{_f(cx + r1 * math.cos(a))}" '
                  f'y2="{_f(cy + r1 * math.sin(a))}" stroke="{col}" stroke-width="1.2" stroke-linecap="round" opacity=".9"/>'
                  f'<circle cx="{_f(cx + (r1 + 2.6) * math.cos(a))}" cy="{_f(cy + (r1 + 2.6) * math.sin(a))}" r=".9" fill="{col}"/>')
    for _ in range(46):
        s += f'<circle cx="{_f(rnd.uniform(0, W))}" cy="{_f(rnd.uniform(3, 62))}" r=".7" fill="#fff" opacity="{rnd.choice((".3", ".5", ".8"))}"/>'
    return s


def _petals(rnd: random.Random) -> str:
    s = ""
    for _ in range(54):
        x, y, a = rnd.uniform(0, W), rnd.uniform(5, GROUND - 2), rnd.uniform(0, 180)
        col = rnd.choice(("#F7B7C9", "#F9CFDA", "#FFFFFF"))
        s += f'<ellipse cx="{_f(x)}" cy="{_f(y)}" rx="2.4" ry="1.2" transform="rotate({_f(a)} {_f(x)} {_f(y)})" fill="{col}" opacity="{rnd.choice((".55", ".75", ".95"))}"/>'
    for x in range(18, W, 34):  # 새싹
        h = rnd.uniform(4, 8)
        xx = x + rnd.uniform(-8, 8)
        s += (f'<path d="M{_f(xx)} {GROUND + 1} v-{_f(h)}" stroke="#A6DB7C" stroke-width="1" opacity=".9"/>'
              f'<path d="M{_f(xx)} {_f(GROUND + 1 - h)} q-4 -3 -5.5 .4 q3 1.6 5.5 -.4 q4 -3.4 5.8 -.2 q-3 2 -5.8 .2" fill="#A6DB7C"/>')
    return s


def _summer(rnd: random.Random) -> str:
    cx, cy = 858, 28
    s = f'<circle cx="{cx}" cy="{cy}" r="13" fill="#FFD166"/>'
    for k in range(12):
        a = math.radians(30 * k)
        s += (f'<line x1="{_f(cx + 18 * math.cos(a))}" y1="{_f(cy + 18 * math.sin(a))}" x2="{_f(cx + 25 * math.cos(a))}" '
              f'y2="{_f(cy + 25 * math.sin(a))}" stroke="#FFD166" stroke-width="2" stroke-linecap="round" opacity=".85"/>')
    for x, y, k in ((210, 26, 1.0), (560, 18, .8), (742, 34, 1.1), (1130, 20, .7), (60, 40, .7)):
        s += (f'<path d="M{_f(x)} {_f(y)} q{_f(4 * k)} -{_f(9 * k)} {_f(14 * k)} -{_f(5 * k)} q{_f(8 * k)} -{_f(8 * k)} {_f(18 * k)} 0 '
              f'q{_f(10 * k)} -{_f(2 * k)} {_f(12 * k)} {_f(5 * k)} z" fill="#EAF9FF" opacity=".2"/>')
    for x, y in ((420, 30), (436, 25), (452, 31), (840, 44), (854, 40)):  # 갈매기
        s += f'<path d="M{x} {y} q3.5 -3.5 6 0 q2.5 -3.5 6 0" stroke="#EAF9FF" stroke-width="1" fill="none" opacity=".6"/>'
    return s


def _leaves(rnd: random.Random) -> str:
    s = '<circle cx="846" cy="24" r="11" fill="#FBE3B0" opacity=".92"/><circle cx="850" cy="21" r="10" fill="#1E2233" opacity=".3"/>'
    for _ in range(46):
        x, y, a = rnd.uniform(0, W), rnd.uniform(5, GROUND + 2), rnd.uniform(0, 360)
        col = rnd.choice(("#F08A3C", "#E9695F", "#F2B233", "#C96A2B"))
        s += (f'<path d="M0 -3.6 Q3.2 -1 0 3.6 Q-3.2 -1 0 -3.6 z" transform="translate({_f(x)} {_f(y)}) rotate({_f(a)})" '
              f'fill="{col}" opacity="{rnd.choice((".6", ".8", ".95"))}"/>')
    return s


def scene_svg(key: str) -> str:
    """계절 장면 SVG(글자 없음). 좁은 화면에서는 가운데가 보이도록 잘린다."""
    t = THEMES[key]
    rnd = random.Random(f"intor-{key}")
    snow = key in ("christmas", "newyear", "winter")
    body = (f'<defs><linearGradient id="ssky-{key}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{t["sky"][0]}"/>'
            f'<stop offset="1" stop-color="{t["sky"][1]}"/></linearGradient>')
    if t["glow"]:
        gx = {"newyear": 600, "spring": 520, "summer": 858, "autumn": 760}[key]
        body += (f'<radialGradient id="sglow-{key}" gradientUnits="userSpaceOnUse" cx="{gx}" cy="{GROUND}" r="330">'
                 f'<stop offset="0" stop-color="{t["glow"][0]}" stop-opacity="{t["glow"][1]}"/>'
                 f'<stop offset="1" stop-color="{t["glow"][0]}" stop-opacity="0"/></radialGradient>')
    body += "</defs>"
    body += f'<rect width="{W}" height="{H}" fill="url(#ssky-{key})"/>'
    if t["glow"]:
        body += f'<rect width="{W}" height="{H}" fill="url(#sglow-{key})"/>'
    if key == "newyear":
        body += _fireworks(rnd)
    elif key == "summer":
        body += _summer(rnd)
    elif key == "autumn":
        body += _leaves(rnd)
    body += _site(t, snow, key == "christmas", rnd)
    if key == "christmas":
        body += _snowfall(rnd, 80, False) + _lights()
    elif key == "winter":
        body += _snowfall(rnd, 110, True)
    elif key == "newyear":
        body += _snowfall(rnd, 28, False)
    elif key == "spring":
        body += _petals(rnd)
    return (f'<svg class="season-art" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMax slice" '
            f'xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">{body}</svg>')


def banner_html(t: dict | None) -> str:
    """웹 지면 마스트헤드 맨 위에 들어가는 계절 띠."""
    if not t:
        return ""
    return (f'<div class="season s-{t["key"]}" role="img" aria-label="{t["label"]}" style="--season-ink:{t["ink"]};--season-bg:{t["sky"][0]}">'
            f'{t["svg"]}<div class="season-txt"><b>{t["en"]}</b><span>{t["msg"]}</span></div></div>')


if __name__ == "__main__":  # 달력 점검: python seasons.py
    for m, d in ((11, 24), (11, 25), (12, 25), (12, 26), (1, 1), (1, 10), (1, 11), (2, 29), (3, 1), (5, 31), (6, 1), (8, 31), (9, 1)):
        y = 2028 if (m, d) == (2, 29) else 2026
        print(f"{m:02d}-{d:02d} → {theme_for(date(y, m, d))}")
