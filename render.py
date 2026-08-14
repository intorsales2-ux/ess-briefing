"""HTML 렌더링 v3 — v10 지면 + 롤링 상태(스포트 3·지식 4) + 등락표 보드 + 보고서 도구."""
from __future__ import annotations
import json
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

BASE = Path(__file__).resolve().parent
STATE = BASE / "output" / "state.json"

BOARD = [  # (마커ID, 지역, 표시명, 티커표기, 기본 기사열 HTML)
    ("373220", "KR", "LG에너지솔루션", "KRX 373220",
     '<a href="https://kr.investing.com/news/stock-market-news/article-2036112" target="_blank" rel="noopener noreferrer">설명회: ESS 4.6배 · 목표 90GWh (7/30)</a>'),
    ("006400", "KR", "삼성SDI", "KRX 006400",
     '<a href="https://www.newsis.com/view/NISX20260730_0003729862" target="_blank" rel="noopener noreferrer">2Q 2,038억 — 7개 분기 만 흑자 (7/30)</a>'),
    ("096770", "KR", "SK이노베이션", "KRX 096770",
     '<a href="https://www.thelec.kr/news/articleView.html?idxno=56239" target="_blank" rel="noopener noreferrer">2차 50.3% · 서산 LFP (5/8)</a> · <a href="https://www.mt.co.kr/industry/2026/07/30/2026073015492916552" target="_blank" rel="noopener noreferrer">SK온 2Q 8,218억 흑자 (7/30)</a>'),
    ("298040", "KR", "효성중공업", "KRX 298040",
     '<a href="https://kr.investing.com/equities/hyosung-heavy-industries" target="_blank" rel="noopener noreferrer">2Q 발표(7/24) — 결과 확인 중</a>'),
    ("TSLA", "GL", "Tesla", "NASDAQ TSLA",
     '<a href="https://www.hankyung.com/article/202607230480i" target="_blank" rel="noopener noreferrer">2Q 저장 13.5GWh · $31.4억 (7/22)</a>'),
    ("FLNC", "GL", "Fluence Energy", "NASDAQ FLNC",
     '<a href="https://www.ess-news.com/2026/07/14/sungrow-leads-first-global-bess-integrator-ranking-as-market-tops-100-gw/" target="_blank" rel="noopener noreferrer">우드맥 SI 랭킹 톱10 (7/14)</a>'),
    ("3750", "GL", "CATL", "HKEX 3750",
     '<a href="https://www.energy-storage.news/2025-bess-cell-and-system-shipments-byd-takes-bess-crown-no-korean-firms-in-top-10-cell-suppliers/" target="_blank" rel="noopener noreferrer">셀 1위 BYD에 내줘 (7/7)</a> · <a href="https://www.ess-news.com/2026/07/14/sungrow-leads-first-global-bess-integrator-ranking-as-market-tops-100-gw/" target="_blank" rel="noopener noreferrer">우드맥 SI 3위 (7/14)</a>'),
    ("300274", "GL", "Sungrow", "SZSE 300274",
     '<a href="https://www.ess-news.com/2026/07/14/sungrow-leads-first-global-bess-integrator-ranking-as-market-tops-100-gw/" target="_blank" rel="noopener noreferrer">우드맥 첫 SI 랭킹 1위 — 연 100GW 시대 (7/14)</a>'),
]

CARD_TPL = '''    <article class="card {cls}">
      <div class="tags">{tags}</div>
      {head}
      <ul class="summary">
{bullets}      </ul>
      <div class="src">{src}</div>
      <div class="insight"><b>{ilabel}</b> — {insight}</div>
      <div class="impact">
        <span class="lab">인투알 영향도</span>
        <span class="soc">{dots}<span class="cap"></span></span>
        <span class="val">{impact_val}</span>
      </div>
    </article>'''


def build_card_html(c: dict) -> str:
    """AI/샘플의 카드 필드 → 손판과 동일한 카드 HTML (스포트·지식 신규분용)."""
    tags = ''.join(f'<span class="tag {t.get("cls", "")}">{t["t"]}</span>' for t in c.get("tags", []))
    if c.get("url"):
        head = (f'<a class="hl" href="{c["url"]}" target="_blank" rel="noopener noreferrer" title="원문 보기">\n'
                f'        <h3>{c["title"]}<span class="ext">↗</span></h3>\n      </a>')
    else:
        head = f'<h3 style="margin:2px 0 10px; font-size:16.5px; line-height:1.45;">{c["title"]}</h3>'
    bullets = ''.join(f'        <li>{b}</li>\n' for b in c.get("bullets", []))
    src = '출처 ' + ' · '.join(
        f'<a href="{s["u"]}" target="_blank" rel="noopener noreferrer">{s["n"]}</a>' for s in c.get("srcs", []))
    if c.get("src_tail"):
        src += ' ' + c["src_tail"]
    n = int(c.get("impact_n", 2))
    dots = ''.join('<i class="on"></i>' if i < n else '<i class=""></i>' for i in range(4))
    html = CARD_TPL.format(cls=c.get("cls", "kr"), tags=tags, head=head, bullets=bullets, src=src,
                           ilabel=c.get("ilabel", "인투알 시사점"), insight=c.get("insight", ""),
                           dots=dots, impact_val=c.get("impact_val", "2/4 중간"))
    if c.get("detail"):
        det = ''.join(f"<p>{p}</p>" for p in c["detail"])
        html = html.replace("</article>", f'  <div class="art-detail" style="display:none">{det}</div>\n    </article>')
    return html


def _load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"next_spot": 1, "next_know": 1, "spot": [], "know": []}


def _board_rows(overrides: dict | None) -> str:
    overrides = overrides or {}
    labels = {"KR": "KOREA — KRX (원)", "GL": "GLOBAL — US · HK · CN"}
    rows, prev_region = [], None
    for sid, reg, name, tk, default_news in BOARD:
        region = labels[reg]
        if region != prev_region:
            rows.append(f'        <tr><th colspan="6" class="region-th">{region}</th></tr>')
            prev_region = region
        cells = ''.join(f'<td class="num"><!--S{sid}:{f}-->—<!--/S{sid}:{f}--></td>' for f in ("PX", "D1", "M1", "Y1"))
        news = overrides.get(sid, default_news)
        rows.append(f'        <tr><td><span class="co-name">{name}</span><span class="tk">{tk}</span></td>'
                    f'{cells}<td>{news}</td></tr>')
    return '\n'.join(rows)


def render_briefing(data: dict) -> str:
    env = Environment(loader=FileSystemLoader(BASE / "templates"),
                      autoescape=False, trim_blocks=True, lstrip_blocks=True)
    template = env.get_template("briefing.j2")

    state = _load_state()
    dry = bool(data.get("_dry"))

    if data.get("new_spot"):
        c = dict(data["new_spot"]); no = c.pop("no", state["next_spot"])
        c.setdefault("cls", "policy"); c.setdefault("ilabel", "에디터의 결론")
        state["spot"].insert(0, {"no": no, "html": build_card_html(c)})
        state["next_spot"] = no + 1
    if data.get("new_know"):
        c = dict(data["new_know"]); no = c.pop("no", state["next_know"])
        c.setdefault("cls", "kr"); c.setdefault("ilabel", "실무 연결")
        c.setdefault("tags", [{"t": f"지식 #{no:03d}", "cls": "t-kr"}, {"t": "기초 과정", "cls": ""}])
        html = build_card_html(c)
        # 지식 카드는 영향도 박스 없음 — 제거
        html = html.split('<div class="impact">')[0].rstrip() + '\n    </article>'
        state["know"].insert(0, {"no": no, "html": html})
        state["next_know"] = no + 1
    dropped_spot = state["spot"][3:]; dropped_know = state["know"][4:]
    state["spot"], state["know"] = state["spot"][:3], state["know"][:4]
    if not dry:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    data.setdefault("spot_note", "최근 3개 롤링(전문 그대로 · 새 글 왼쪽)"
                    + (f" — #{dropped_spot[0]['no']:03d} 지면 졸업" if dropped_spot else ""))
    data.setdefault("know_note", "최근 4개 롤링 — 전문 그대로 유지(요약·축소 없음), 새 지식이 왼쪽"
                    + (f" — #{dropped_know[0]['no']:03d} 지면 졸업" if dropped_know else ""))
    data["spot_cards_html"] = '\n'.join(s["html"] for s in state["spot"])
    data["know_cards_html"] = '\n'.join(k["html"] for k in state["know"])
    data["board_rows_html"] = _board_rows(data.get("board_news"))
    data["style_block"] = (BASE / "assets" / "style_base.css.html").read_text(encoding="utf-8")
    tool = (BASE / "assets" / "report_tool.html").read_text(encoding="utf-8")
    cmt_api = (data.get("comments_api_url") or "").strip()
    data["report_tool"] = tool.replace("__CMT_API__", cmt_api)
    logo_b64 = (BASE / "assets" / "logo_b64.txt").read_text(encoding="utf-8").strip()
    return template.render(logo_b64=logo_b64, **data)


def render_to_file(data: dict, out_path: Path) -> Path:
    html = render_briefing(data)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    sample = json.loads((BASE / "data" / "sample_data.json").read_text(encoding="utf-8"))
    sample["_dry"] = True
    out = render_to_file(sample, BASE / "output" / "index.html")
    print(f"rendered → {out} ({out.stat().st_size:,} bytes)")
