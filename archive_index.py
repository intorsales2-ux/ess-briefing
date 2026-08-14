"""archive_index.py — 지난 호 게시판(docs/list.html) 생성

docs/archive/*.html 을 훑어 호수·날짜·3줄 요약 첫 줄을 뽑아 목록 페이지를 만든다.
발행 후 호출: python archive_index.py
"""
from __future__ import annotations

import re
from pathlib import Path

DOCS = Path(__file__).parent / "docs"
ARCH = DOCS / "archive"

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#070b0f;color:#e6edf3;font-family:'Malgun Gothic','Apple SD Gothic Neo',-apple-system,sans-serif;line-height:1.6;padding:20px 14px 60px}
.wrap{max-width:860px;margin:0 auto}
.head{background:#0e1720;border:1px solid #1f2a36;border-radius:14px;padding:20px 22px;margin-bottom:16px}
.brand{font-size:22px;font-weight:900;letter-spacing:1px}
.brand span{color:#4dd0a4}
.sub{color:#9aa4b2;font-size:12.5px;margin-top:6px}
.latest{display:block;background:linear-gradient(135deg,#12303f,#0e1720);border:1px solid #2b6b57;border-radius:14px;padding:18px 20px;margin-bottom:22px;text-decoration:none;color:inherit}
.latest .tag{display:inline-block;background:#4dd0a4;color:#07130d;font-size:11px;font-weight:800;padding:3px 10px;border-radius:12px;margin-bottom:8px}
.latest h2{font-size:17px;margin-bottom:6px}
.latest p{color:#b9c4cf;font-size:13px}
.sec{color:#6b7684;font-size:11.5px;letter-spacing:.12em;margin:0 0 10px 4px}
.row{display:flex;align-items:center;gap:14px;background:#0b131b;border:1px solid #1a2530;border-radius:11px;padding:13px 16px;margin-bottom:8px;text-decoration:none;color:inherit}
.row:hover{border-color:#4dd0a4;background:#0e1a24}
.d{flex:0 0 96px;font-size:12.5px;color:#9aa4b2;font-variant-numeric:tabular-nums}
.d em{display:block;font-style:normal;font-size:10.5px;color:#6b7684}
.t{flex:1;min-width:0}
.t b{font-size:13.5px;color:#e6edf3}
.lead{display:block;color:#8e9aa6;font-size:12px;margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.go{flex:0 0 auto;color:#4dd0a4;font-size:12px;font-weight:700}
.foot{color:#4a5560;font-size:11px;text-align:center;margin-top:26px}
@media(max-width:560px){
  .row{flex-wrap:wrap;gap:6px}
  .d{flex:0 0 auto} .d em{display:inline;margin-left:6px}
  .t{flex:1 0 100%} .go{display:none}
  .lead{white-space:normal}
}
"""


def _meta(html: str) -> dict:
    issue = re.search(r"제(20\d\d-\d+)호", html)
    pub = re.search(r"발행 (20\d\d\.\d\d\.\d\d)\(([^)]+)\)", html)
    lead = re.search(r'<li><span class="n">1</span><div><b>(.{10,220}?)</b>', html, re.S)
    lead_txt = re.sub(r"<[^>]+>", "", lead.group(1)).strip() if lead else ""
    return {
        "issue": "제" + issue.group(1) + "호" if issue else "",
        "date": pub.group(1) if pub else "",
        "dow": pub.group(2) if pub else "",
        "lead": lead_txt[:150],
    }


def build() -> Path:
    rows = []
    for f in sorted(ARCH.glob("*.html"), reverse=True):
        try:
            m = _meta(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        m["file"] = "archive/" + f.name
        m["ymd"] = f.stem
        rows.append(m)

    parts = []
    for r in rows:
        lead = '<span class="lead">' + r["lead"] + "</span>" if r["lead"] else ""
        parts.append(
            '      <a class="row" href="' + r["file"] + '">'
            '<span class="d">' + r["ymd"] + "<em>" + r["dow"] + "</em></span>"
            '<span class="t"><b>' + r["issue"] + "</b>" + lead + "</span>"
            '<span class="go">&rarr;</span></a>'
        )
    items = "\n".join(parts)

    latest_block = ""
    if rows:
        L = rows[0]
        latest_block = (
            '  <a class="latest" href="index.html">'
            '<span class="tag">최신호</span>'
            "<h2>" + L["issue"] + " · " + L["date"] + "(" + L["dow"] + ")</h2>"
            "<p>" + L["lead"] + "</p></a>"
        )

    html = (
        '<!DOCTYPE html>\n<html lang="ko"><head><meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        "<title>인투알 ESS 데일리 브리핑 — 지난 호</title>\n"
        "<style>" + CSS + "</style></head>\n"
        '<body><div class="wrap">\n'
        '  <div class="head">\n'
        '    <div class="brand">INTO<span>R</span> · ESS DAILY BRIEFING</div>\n'
        '    <div class="sub">2차전지 외함(컨테이너·랙) 사업 관점의 시장·입찰·업계 동향 · &copy; 인투알 영업팀 내부용</div>\n'
        "  </div>\n"
        + latest_block + "\n"
        '  <div class="sec">지난 호 · ' + str(len(rows)) + "건</div>\n"
        + items + "\n"
        '  <div class="foot">매 영업일 07:30 자동 발행 · 각 지면 맨 아래에서 댓글로 의견을 남길 수 있습니다</div>\n'
        "</div></body></html>\n"
    )

    DOCS.mkdir(exist_ok=True)
    out = DOCS / "list.html"
    out.write_text(html, encoding="utf-8")
    print("[archive] 게시판 갱신 -> " + str(out) + " (" + str(len(rows)) + "건)")
    return out


if __name__ == "__main__":
    build()
