"""HTML 렌더링 v3 — v10 지면 + 롤링 상태(스포트 3·지식 4) + 등락표 보드 + 보고서 도구."""
from __future__ import annotations
import json
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

BASE = Path(__file__).resolve().parent
STATE = BASE / "output" / "state.json"

BOARD = [  # (마커ID, 그룹, 표시명, 티커, 기본 기사열)
    ("373220", "CELL", "LG에너지솔루션", "KRX 373220", "설명회: ESS 4.6배 · 목표 90GWh"),
    ("006400", "CELL", "삼성SDI", "KRX 006400", "2Q 2,038억 — 7분기 만 흑자"),
    ("096770", "CELL", "SK이노베이션", "KRX 096770", "SK온 2Q 8,218억 흑자"),
    ("247540", "CELL", "에코프로비엠", "KRX 247540", "ESS용 LFP 양극재 전환 관전"),
    ("298040", "GRID", "효성중공업", "KRX 298040", "2Q 2,643억 분기 최대 · 잔고 17.5조"),
    ("267260", "GRID", "HD현대일렉트릭", "KRX 267260", "변압기 슈퍼사이클 — 북미 수주"),
    ("010120", "GRID", "LS일렉트릭", "KRX 010120", "배전 · ESS PCS 라인업"),
    ("000880", "GRID", "한화", "KRX 000880", "한화솔루션 — 국내 ESS SI"),
    ("TSLA", "GL", "Tesla", "NASDAQ TSLA", "2Q 저장 13.5GWh · $31.4억"),
    ("FLNC", "GL", "Fluence Energy", "NASDAQ FLNC", "우드맥 SI 톱10"),
    ("300274", "GL", "Sungrow", "SZSE 300274", "우드맥 첫 SI 랭킹 1위 — 연 100GW"),
    ("3750", "GL", "CATL", "HKEX 3750", "셀 1위 BYD에 내줘"),
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
    """주가 보드 — 카드 격자(그룹 헤더 + 12종목)."""
    overrides = overrides or {}
    labels = {"CELL": "KOREA — 셀 · 소재", "GRID": "KOREA — 전력기기 · EPC", "GL": "GLOBAL — 셀 · SI"}
    out, prev = [], None
    for sid, grp, name, tk, default_news in BOARD:
        if grp != prev:
            out.append(f'      <div class="qsec">{labels[grp]}</div>')
            prev = grp
        px = f'<!--S{sid}:PX-->—<!--/S{sid}:PX-->'
        dd = ''.join(f'<span><!--S{sid}:{f}-->—<!--/S{sid}:{f}--></span>' for f in ("D1", "M1", "Y1"))
        news = overrides.get(sid, default_news)
        out.append(f'      <div class="qcard">'
                   f'<div class="nm"><span>{name}</span><span class="tk">{tk}</span></div>'
                   f'<div class="px">{px}</div>'
                   f'<div class="dd">{dd}</div>'
                   f'<div class="nx">{news}</div></div>')
    return '\n'.join(out)

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
    state["spot"], state["know"] = state["spot"][:1], state["know"][:1]
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
