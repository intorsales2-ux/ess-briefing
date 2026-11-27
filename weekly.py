"""주간 코너 — 그 주의 첫 호(보통 월요일): AI 활용 교실 / 금요일: 주간 퀴즈.

두 코너 모두 본 지면과 별도 호출로 만든다. 실패하면 그 주 코너만 빠지고 지면은 정상 발행된다.
- AI 활용 교실: #001은 고정 원고, #002~#012는 아래 강의 계획(SYLLABUS)에 따라 집필, 이후는 자율 주제.
- 주간 퀴즈: 이번 주에 실제 발행된 지면 텍스트에서만 출제한다. 문제마다 근거 구절을 받아
  그 구절이 해당 호 지면에 그대로 있는지 코드가 대조하고, 대조에 실패한 문제는 버린다.
  점수는 어디에도 저장·전송하지 않는다(자체 확인용).
"""
from __future__ import annotations

import html as _html
import json
import random
import re
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]

# ───────────────────────── AI 활용 교실 ─────────────────────────
LESSON_001 = {
    "title": "AI에게 일 시키는 법 ① — 좋은 지시문의 4요소",
    "lead": "같은 AI라도 어떻게 시키느냐에 따라 결과가 크게 달라집니다. 신입 사원에게 업무를 넘길 때처럼 네 가지만 알려주면 됩니다. 어떤 AI 도구에서든 통하는 방법입니다.",
    "points": [
        {"h": "역할", "t": "누구의 입장에서 답할지 정해줍니다.", "eg": "너는 ESS 외함 제조사의 해외영업 담당자다"},
        {"h": "맥락", "t": "어떤 상황이고 누가 읽을 자료인지 알려줍니다.", "eg": "고객이 보낸 견적 요청 메일이고, 팀장에게 보고할 자료다"},
        {"h": "작업", "t": "무엇을 해야 하는지 구체적으로 적습니다.", "eg": "요구 사양, 회신할 질문, 모호한 부분을 뽑아라"},
        {"h": "형식", "t": "결과물의 모양과 분량을 정해줍니다.", "eg": "한국어 표로, 항목당 한 줄"},
    ],
    "bad": {"label": "이렇게만 시키면 결과가 밋밋합니다", "text": "이 메일 요약해줘"},
    "prompt": {"label": "4요소를 넣은 지시문 — 복사해서 바로 써보세요", "text": (
        "너는 ESS 외함 제조사의 해외영업 담당자다.\n"
        "아래는 해외 고객이 보낸 영문 견적 요청(RFQ) 메일이고, 팀장에게 보고할 자료를 만들려고 한다.\n\n"
        "다음 세 가지를 한국어 표로 정리해줘. 항목당 한 줄로.\n"
        "1) 고객이 요구한 사양 (수량, 납기, 인증, 규격)\n"
        "2) 우리가 회신해야 할 질문\n"
        "3) 메일만으로는 알 수 없어 확인이 필요한 부분\n\n"
        "메일에 없는 내용은 추측하지 말고 \"확인 필요\"라고 써줘.\n\n"
        "[여기에 메일 본문 붙여넣기]")},
    "notes": [
        {"h": "주의 ① 보안", "t": "고객 도면, 단가, NDA 대상 자료는 회사가 허용한 AI 도구에만 넣습니다. 헷갈리면 넣기 전에 먼저 확인하세요."},
        {"h": "주의 ② 검증", "t": "숫자, 날짜, 규격명은 반드시 원문과 대조합니다. AI는 그럴듯하게 틀릴 수 있습니다."},
        {"h": "이번 주 실습", "t": "오늘 받은 메일 한 통으로 위 지시문을 그대로 써보세요."},
    ],
}

SYLLABUS = {  # 강의 번호 → (주제, 꼭 담을 내용)
    2: ("긴 문서(사양서·계약서)를 요약시키는 법", "요약의 목적과 읽을 사람을 먼저 알려주기, 조항·쪽 번호 등 근거 위치를 함께 적게 하기, '빠뜨린 것이 있나' 되묻기"),
    3: ("영문 메일 초안과 답장 쓰기", "전하려는 핵심 3가지를 한국어로 먼저 주기, 톤과 분량 지정, 보내기 전 사람 이름·숫자·날짜 직접 확인"),
    4: ("회의록·통화 메모 정리하기", "결정 사항 / 할 일 / 담당 / 기한 표로 뽑게 하기, 말하지 않은 내용은 지어내지 못하게 하기"),
    5: ("표와 숫자 다루기", "견적·사양 비교표 만들게 하기, 단위·통화·환율 기준 명시, 계산 결과는 엑셀로 검산"),
    6: ("번역 품질 높이는 법", "우리 용어집(외함=enclosure 등) 먼저 주기, 직역과 의역 구분해서 요청, 거꾸로 번역시켜 뜻이 유지되는지 확인"),
    7: ("AI에게 반론과 빠진 점 받기", "내 초안의 약점 5가지 묻기, 고객·경쟁사 입장에서 질문하게 하기, 좋은 말만 하지 않게 지시하기"),
    8: ("자료 조사시킬 때의 주의", "출처와 날짜를 함께 요구하기, 한 곳만 믿지 않고 교차 확인, 최신 정보는 틀릴 수 있음을 전제하기"),
    9: ("보고서 초안 다듬기", "초안은 내가 쓰고 다듬기를 맡기기, 결론 먼저·문장 짧게, 바꾼 곳을 표시하게 하기"),
    10: ("반복 업무를 지시문 틀로 만들기", "자주 쓰는 지시문을 저장해 재사용, 바뀌는 부분만 [자리표시]로 남기기, 팀과 공유하기"),
    11: ("AI가 틀리는 순간 알아채기", "그럴듯한 숫자·없는 규격·없는 출처, 확인 체크리스트, 틀렸을 때 다시 묻는 법"),
    12: ("보안과 사내 규정 총정리", "넣어도 되는 자료와 안 되는 자료 구분, 고객명·단가 가리고 묻는 법, 결과물의 책임은 사람에게"),
}

CLASS_SYSTEM = """당신은 '인투알'(ESS 외함·컨테이너 제조사) 사내 소식지의 'AI 활용 교실' 필자다. 독자는 영업·구매·설계·생산관리 등 비개발 직군이다.
원칙:
1. 특정 AI 제품의 이름·메뉴·기능·가격은 쓰지 않는다(바뀌기 쉽다). 어떤 대화형 AI에서도 통하는 방법만 쓴다.
2. 한 번에 한 가지 기술만, 읽고 바로 따라 할 수 있게 쓴다. 예시는 ESS 외함 제조사의 업무 상황(견적 요청 메일, 사양서, 회의록, 납기 조율 등)으로 든다.
3. 지시문 예시(prompt.text)는 복사해서 바로 쓸 수 있어야 한다. 실제 회사명·고객명·수치는 넣지 않고 [대괄호] 자리표시로 둔다.
4. notes에는 이번 주제에 맞는 주의 2가지(보안: 고객 도면·단가·NDA 자료는 회사가 허용한 AI 도구에만 / 검증: 숫자·날짜·규격은 원문과 대조 — 중 해당하는 것)와 '이번 주 실습' 1가지를 넣는다.
5. 과장하지 않는다. AI는 틀릴 수 있고 최종 확인은 사람이 한다는 전제를 유지한다.
6. 말투는 '~합니다' 체, 문장은 짧게. 출력은 JSON 하나만 — 다른 텍스트·마크다운 금지."""


def _e(s) -> str:
    return _html.escape(str(s), quote=False)


def class_html(lesson: dict, no: int, next_title: str = "") -> str:
    pts = "".join(
        f'<li><span class="k">{i}</span><div><b>{_e(p.get("h", ""))}</b> — {_e(p.get("t", ""))}'
        + (f'<span class="eg">“{_e(p["eg"])}”</span>' if p.get("eg") else "") + "</div></li>"
        for i, p in enumerate(lesson.get("points", [])[:4], 1))
    bad = lesson.get("bad") or {}
    bad_html = (f'<div class="pr bad"><div class="pr-h"><span>{_e(bad.get("label", "이렇게만 시키면 아쉽습니다"))}</span></div>'
                f'<pre>{_e(bad.get("text", ""))}</pre></div>') if bad.get("text") else ""
    pr = lesson.get("prompt") or {}
    notes = "".join(f'<div class="wk-note"><b>{_e(n.get("h", ""))}</b> — {_e(n.get("t", ""))}</div>'
                    for n in lesson.get("notes", [])[:3])
    if next_title:
        notes += f'<div class="wk-note"><b>다음 주 #{no + 1:03d}</b> — {_e(next_title)}.</div>'
    return f'''  <section class="wk" aria-labelledby="wk-ai-t">
    <div class="wk-head"><span class="wk-day">매주 월요일</span><span class="wk-no">AI 활용 교실 #{no:03d}</span></div>
    <h3 id="wk-ai-t">{_e(lesson.get("title", ""))}</h3>
    <p class="wk-lead">{_e(lesson.get("lead", ""))}</p>
    <div class="wk-grid">
      <div>
        <ol class="wk-four">{pts}</ol>
        {bad_html}
      </div>
      <div>
        <div class="pr"><div class="pr-h"><span>{_e(pr.get("label", "복사해서 바로 써보세요"))}</span><button type="button" id="pr-copy">복사</button></div><pre id="pr-text">{_e(pr.get("text", ""))}</pre></div>
      </div>
    </div>
    <div class="wk-notes">{notes}</div>
  </section>
<script>
(function(){{
  var b = document.getElementById('pr-copy'), t = document.getElementById('pr-text'); if (!b || !t) return;
  function done(){{ b.textContent = '복사됨'; setTimeout(function(){{ b.textContent = '복사'; }}, 1600); }}
  function fallback(){{
    var r = document.createRange(); r.selectNodeContents(t);
    var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
    try {{ document.execCommand('copy'); done(); }} catch (e) {{}}
    sel.removeAllRanges();
  }}
  b.addEventListener('click', function(){{
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(t.textContent).then(done, fallback);
    else fallback();
  }});
}})();
</script>'''


def _valid_lesson(d) -> bool:
    try:
        return (bool(str(d["title"]).strip()) and bool(str(d["lead"]).strip())
                and 2 <= len(d["points"]) <= 4 and all(p.get("h") and p.get("t") for p in d["points"])
                and len(str(d["prompt"]["text"]).strip()) >= 40 and len(d.get("notes", [])) >= 2)
    except Exception:
        return False


def week_key(now: datetime) -> str:
    y, w, _ = now.isocalendar()
    return f"{y}-W{w:02d}"


def class_due(state: dict, now: datetime) -> bool:
    """이번 주에 아직 AI 활용 교실이 안 나갔으면 True — 보통 월요일, 월요일 발행이 없었으면 그 주 첫 호."""
    return state.get("class_week") != week_key(now)


def make_class(state: dict, now: datetime, call_json) -> dict | None:
    """AI 활용 교실 한 편. 반환: {html, no, title, state(갱신할 값)} 또는 None(이번 주는 생략)."""
    no = int(state.get("next_class", 1))
    past = list(state.get("class_titles", []))
    nxt = SYLLABUS.get(no + 1, ("", ""))[0]
    if no == 1:
        lesson = LESSON_001
    else:
        topic, must = SYLLABUS.get(no, ("", ""))
        ask = (f"이번 주제: {topic}\n꼭 담을 내용: {must}" if topic else
               "이번 주제: 지금까지 다루지 않은 실무 주제를 스스로 정한다(지난 주제와 겹치지 않게).")
        prompt = f"""'AI 활용 교실' #{no:03d} 원고를 쓴다.
{ask}
지난 주제: {json.dumps(past[-20:], ensure_ascii=False)}

아래는 형식 예시(#001)다. 같은 구조·분량으로 쓴다.
{json.dumps(LESSON_001, ensure_ascii=False, indent=1)}

출력 JSON 스키마:
{{"title": "제목(40자 이내)", "lead": "도입 2~3문장", "points": [{{"h": "핵심어", "t": "설명 한 문장", "eg": "짧은 예시(따옴표 없이)"}} 3~4개],
 "bad": {{"label": "이렇게만 시키면 …", "text": "아쉬운 지시문 예(한 줄)"}},
 "prompt": {{"label": "… — 복사해서 바로 써보세요", "text": "여러 줄 지시문(자리표시는 [대괄호])"}},
 "notes": [{{"h": "주의 ① …", "t": "…"}}, {{"h": "주의 ② …", "t": "…"}}, {{"h": "이번 주 실습", "t": "…"}}]}}"""
        try:
            lesson = call_json(prompt, max_tokens=12000, system=CLASS_SYSTEM, label="AI 활용 교실 집필")
        except Exception as exc:
            print(f"[weekly] AI 활용 교실 생성 실패({type(exc).__name__}: {str(exc)[:120]}) — 이번 주는 생략")
            return None
        if not _valid_lesson(lesson):
            print("[weekly] AI 활용 교실 원고가 규격에 맞지 않습니다 — 이번 주는 생략")
            return None
    title = str(lesson["title"]).strip()
    return {"html": class_html(lesson, no, nxt), "no": no, "title": title, "kind": "class",
            "label": f"AI 활용 교실 #{no:03d} — {title}",
            "state": {"next_class": no + 1, "class_week": week_key(now), "class_titles": (past + [title])[-30:]}}


# ───────────────────────── 주간 퀴즈 ─────────────────────────
QUIZ_SYSTEM = """당신은 인투알 ESS 데일리 브리핑의 '주간 퀴즈' 출제자다. 이번 주 지면에 실제로 실린 내용만으로 문제를 낸다.
원칙:
1. 정답은 반드시 제공된 지면 텍스트에 그대로 나오는 사실이어야 한다. 지면에 없는 지식으로 출제하지 않는다.
2. 각 문제의 evidence에는 정답의 근거 구절을 해당 날짜의 지면 텍스트에서 '그대로 복사'해 넣는다(12~60자, 한 글자도 바꾸지 않는다).
3. 가능한 한 서로 다른 날의 지면에서 고르게 낸다.
4. 보기는 4개, 정답은 1개. 오답은 그럴듯하되 지면 내용과 명백히 달라야 한다.
5. 지엽적인 숫자 암기보다 '이번 주에 무슨 일이 있었나'를 묻는다. 계산 문제는 1문제 이하.
6. 해설(ex)은 1~2문장 — 왜 정답인지와 외함·랙 제조사에게 무슨 의미인지. '~합니다' 체.
7. 출력은 JSON 하나만 — 다른 텍스트·마크다운 금지."""


def _norm(s: str) -> str:
    s = _html.unescape(re.sub(r"<[^>]+>", "", s or ""))
    for a, b in (("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"'), ("·", "·")):
        s = s.replace(a, b)
    return re.sub(r"\s+", "", s)


def issue_text_from_html(page: str) -> dict:
    """발행된 지면 HTML → 퀴즈 출제용 텍스트(3줄 요약 · 카드 제목과 요점 · 단신)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(page, "html.parser")
    for x in soup.select(".art-detail, script, style"):
        x.decompose()
    lines = []
    for li in soup.select("section.brief li"):
        lines.append("요약: " + li.get_text(" ", strip=True)[1:].strip())
    for art in soup.select("article.card"):
        h = art.select_one("h3")
        if h:
            lines.append("기사: " + h.get_text(" ", strip=True).replace("↗", "").strip())
        for li in art.select("ul.summary li"):
            lines.append(" - " + li.get_text(" ", strip=True))
    for tr in soup.select("section.board tbody tr"):
        tds = tr.find_all("td")
        if len(tds) >= 2:
            lines.append("단신: " + tds[1].get_text(" ", strip=True))
    m = re.search(r"제(20\d\d-\d+)호", page)
    return {"issue": f"제{m.group(1)}호" if m else "", "text": "\n".join(lines)}


def issue_text_from_data(data: dict) -> dict:
    """오늘 호(아직 파일이 되기 전)의 데이터 → 같은 형태의 텍스트."""
    strip = lambda s: re.sub(r"<[^>]+>", "", str(s or ""))
    lines = [f"요약: {strip(l.get('head'))} {strip(l.get('body'))}" for l in data.get("three_lines", [])]
    cards = [c for s in data.get("news_sections", []) for c in s.get("cards", [])]
    cards += [c for c in (data.get("new_spot"), data.get("new_know")) if c]
    for c in cards:
        lines.append("기사: " + strip(c.get("title")))
        lines += [" - " + strip(b) for b in c.get("bullets", [])]
    lines += ["단신: " + strip(b.get("txt")) for b in data.get("briefs", [])]
    return {"issue": data.get("issue_no", ""), "text": "\n".join(lines)}


def week_issues(now: datetime, today: dict | None, archive_dir: Path) -> list[dict]:
    """이번 주 월요일부터 오늘까지 실제 발행된 호. 오늘 호는 today(데이터에서 뽑은 텍스트)를 쓴다."""
    monday = now - timedelta(days=now.weekday())
    out = []
    for k in range(now.weekday() + 1):
        d = monday + timedelta(days=k)
        ymd = d.strftime("%Y-%m-%d")
        if k == now.weekday() and today:
            info = dict(today)
        else:
            f = archive_dir / f"{ymd}.html"
            if not f.exists():
                continue
            try:
                info = issue_text_from_html(f.read_text(encoding="utf-8"))
            except Exception:
                continue
        if not info.get("text", "").strip():
            continue
        info.update(date=ymd, md=f"{d.month}/{d.day}", dow=WEEKDAY_KO[d.weekday()])
        out.append(info)
    return out


def check_questions(raw, issues: list[dict]) -> list[dict]:
    """출제 결과 검증 — 날짜가 이번 주 지면이고, 근거 구절이 그 호 텍스트에 그대로 있는 문제만 통과."""
    by_date = {i["date"]: i for i in issues}
    good = []
    for q in (raw.get("questions", []) if isinstance(raw, dict) else []):
        try:
            iss = by_date[str(q["date"]).strip()]
            opts = [str(o).strip() for o in q["o"]]
            a = int(q["a"])
            ev = _norm(str(q["evidence"]))
            if len(opts) != 4 or len(set(opts)) != 4 or not (0 <= a <= 3) or not str(q["q"]).strip():
                continue
            if len(ev) < 8 or ev not in _norm(iss["text"]):
                continue
            order = list(range(4))
            random.Random(f'{q["date"]}|{q["q"]}').shuffle(order)  # 정답 위치 섞기(날짜·문제 기준 고정)
            good.append({"date": iss["date"], "day": f'{iss["dow"]} {iss["md"]} · {iss["issue"]}'.strip(" ·"),
                         "q": str(q["q"]).strip(), "o": [opts[i] for i in order], "a": order.index(a),
                         "ex": str(q.get("ex", "")).strip()})
        except Exception:
            continue
    return good


def quiz_html(questions: list[dict], span: str, site_url: str) -> str:
    base = (site_url.rstrip("/") + "/") if site_url else ""
    qz = [{"day": q["day"], "url": f'{base}archive/{q["date"]}.html', "q": q["q"], "o": q["o"], "a": q["a"], "ex": q["ex"]}
          for q in questions]
    data = json.dumps(qz, ensure_ascii=False).replace("</", "<\\/")
    n = len(qz)
    return f'''  <section class="wk" id="qz" aria-labelledby="wk-qz-t">
    <div class="wk-head"><span class="wk-day">매주 금요일</span><span class="wk-no">주간 퀴즈</span></div>
    <h3 id="wk-qz-t">이번 주 지면, 다 보셨나요? — {n}문제</h3>
    <p class="wk-lead">이번 주({span}) 지면에서 출제했습니다. <b class="self">자체 확인용</b>이며, 점수는 어디에도 저장·전송되지 않고 이 화면에서만 보입니다.</p>
    <div class="qz-top"><span class="qz-prog" id="qz-prog">문제 1 / {n}</span><span class="qz-dots" id="qz-dots" aria-hidden="true"></span></div>
    <div id="qz-body"></div>
    <noscript><p class="wk-lead">퀴즈는 웹 브라우저에서 지면을 열면 풀 수 있습니다.</p></noscript>
  </section>
<script>
/* 주간 퀴즈 — 자체 확인용(점수 저장·전송 없음) */
(function(){{
  var QZ = {data};
  var box = document.getElementById('qz-body'); if (!box) return;
  var dots = document.getElementById('qz-dots'), prog = document.getElementById('qz-prog');
  var idx = 0, picks = [];
  function esc(s){{ var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }}
  function paintDots(){{
    var h = '';
    for (var i = 0; i < QZ.length; i++){{
      var c = i < picks.length ? (picks[i] === QZ[i].a ? 'ok' : 'no') : (i === idx ? 'cur' : '');
      h += '<i class="' + c + '"></i>';
    }}
    dots.innerHTML = h;
  }}
  function show(){{
    var q = QZ[idx];
    prog.textContent = '문제 ' + (idx + 1) + ' / ' + QZ.length;
    paintDots();
    var h = '<div class="qz-src">출제: ' + esc(q.day) + '</div><div class="qz-q">' + esc(q.q) + '</div><div class="qz-opts">';
    for (var i = 0; i < q.o.length; i++) h += '<button type="button" data-i="' + i + '">' + esc(q.o[i]) + '</button>';
    h += '</div><div class="qz-fb" id="qz-fb" role="status" aria-live="polite" hidden></div>';
    box.innerHTML = h;
    var btns = box.querySelectorAll('.qz-opts button');
    for (var b = 0; b < btns.length; b++) btns[b].addEventListener('click', pick);
  }}
  function pick(e){{
    var q = QZ[idx], i = parseInt(e.currentTarget.getAttribute('data-i'), 10);
    picks.push(i);
    var btns = box.querySelectorAll('.qz-opts button');
    for (var b = 0; b < btns.length; b++){{
      btns[b].disabled = true;
      if (b === q.a) btns[b].className = 'ok';
      else if (b === i) btns[b].className = 'no';
    }}
    var fb = document.getElementById('qz-fb');
    fb.hidden = false;
    fb.innerHTML = '<b>' + (i === q.a ? '정답입니다.' : '아쉽습니다. 정답은 “' + esc(q.o[q.a]) + '”입니다.') + '</b> ' + esc(q.ex)
      + ' <a href="' + q.url + '" target="_blank" rel="noopener noreferrer">해당 호 다시 보기</a>'
      + '<div><button type="button" class="qz-next" id="qz-next">' + (idx < QZ.length - 1 ? '다음 문제' : '결과 보기') + '</button></div>';
    paintDots();
    var nx = document.getElementById('qz-next');
    nx.addEventListener('click', function(){{ idx++; if (idx < QZ.length) show(); else end(); }});
    nx.focus({{preventScroll: true}});
  }}
  function end(){{
    var s = 0, miss = [];
    for (var i = 0; i < QZ.length; i++){{ if (picks[i] === QZ[i].a) s++; else miss.push(QZ[i]); }}
    prog.textContent = '완료';
    paintDots();
    var msg = s === QZ.length ? '이번 주 지면을 꼼꼼히 보셨습니다.' : (s * 2 >= QZ.length ? '핵심은 잡으셨습니다.' : '놓친 호를 한 번 훑어보시면 좋겠습니다.');
    var h = '<div class="qz-end"><div class="score" id="qz-score">' + s + ' <small>/ ' + QZ.length + '</small></div><div class="qz-msg">' + msg + '</div>';
    if (miss.length){{
      h += '<div class="qz-miss">다시 볼 호: ';
      for (var m = 0; m < miss.length; m++) h += '<a href="' + miss[m].url + '" target="_blank" rel="noopener noreferrer">' + esc(miss[m].day) + '</a>' + (m < miss.length - 1 ? ' · ' : '');
      h += '</div>';
    }}
    h += '<div class="qz-self">자체 확인용 점수입니다. 어디에도 저장·전송되지 않으며 이 화면에서만 보입니다.</div>'
       + '<button type="button" class="qz-next" id="qz-again">다시 풀기</button></div>';
    box.innerHTML = h;
    document.getElementById('qz-again').addEventListener('click', function(){{ idx = 0; picks = []; show(); }});
  }}
  show();
}})();
</script>'''


def make_quiz(now: datetime, data: dict, site_url: str, call_json, archive_dir: Path | None = None) -> dict | None:
    """금요일 주간 퀴즈. 반환: {html, label, n} 또는 None(생략)."""
    issues = week_issues(now, issue_text_from_data(data), archive_dir or (BASE / "docs" / "archive"))
    if not issues:
        print("[weekly] 이번 주 지면을 찾지 못했습니다 — 퀴즈 생략")
        return None
    body = "\n\n".join(f'[{i["date"]} ({i["dow"]}) {i["issue"]}]\n{i["text"]}' for i in issues)
    prompt = f"""이번 주 지면 {len(issues)}개 호의 텍스트다.

{body}

위 내용에서만 5문제를 낸다. 날짜는 위 대괄호의 날짜(YYYY-MM-DD)를 그대로 쓴다.
출력 JSON 스키마:
{{"questions": [{{"date": "YYYY-MM-DD", "q": "문제(존댓말 의문문)", "o": ["보기1", "보기2", "보기3", "보기4"], "a": 정답 위치(0~3), "ex": "해설 1~2문장", "evidence": "해당 호 텍스트에서 그대로 복사한 근거 구절"}} x5]}}"""
    try:
        raw = call_json(prompt, max_tokens=12000, system=QUIZ_SYSTEM, label="주간 퀴즈 출제")
    except Exception as exc:
        print(f"[weekly] 퀴즈 생성 실패({type(exc).__name__}: {str(exc)[:120]}) — 이번 주는 생략")
        return None
    good = check_questions(raw, issues)[:5]
    n_raw = len(raw.get("questions", [])) if isinstance(raw, dict) else 0
    print(f"[weekly] 퀴즈 {n_raw}문제 중 근거 대조 통과 {len(good)}문제")
    if len(good) < 3:
        print("[weekly] 통과 문제가 3개 미만 — 이번 주 퀴즈는 생략")
        return None
    span = f'{issues[0]["md"]}~{issues[-1]["md"]}' if len(issues) > 1 else issues[0]["md"]
    return {"html": quiz_html(good, span, site_url), "n": len(good), "kind": "quiz",
            "label": f"주간 퀴즈 — 이번 주 지면 {len(good)}문제(자체 확인용)", "state": {}}
