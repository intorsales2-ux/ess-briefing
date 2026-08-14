"""AI 모듈 — Claude API로 기사 선별·요약·시사점·To-Do 생성."""
from __future__ import annotations
import json
import os
import re

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

SYSTEM = """당신은 '인투알'(2차전지 ESS 외함·컨테이너·랙 제조사) 영업팀의 데일리 브리핑 에디터다. 규칙(v10 요약):
1. 사실만: 입력으로 받은 기사에 없는 사실·숫자·시세를 절대 지어내지 않는다. URL은 입력 기사의 것만 사용.
2. 재탕 금지: 입력 기사는 이미 기출·신선도 필터를 통과했다. 카드마다 발행일을 표기한다.
3. 카드: 불릿 2~4개(핵심 숫자 <b> 강조), '인투알 시사점'(외함·랙 관점 필수), 영향도 1~4, detail(보고서용 상세 해설 3~4문단 — 배경·경과·숫자 분해·인투알 액션. 원문 전재 금지, 해설로 작성).
4. 최소 지면: 카드 6·단신 5 목표 — 재료가 부족하면 지어내지 말고 mast.counts에 사유를 쓴다.
5. 스포트라이트(new_spot): 매일 1건 자율 선정 — 뉴스 재탕이 아닌 '숫자 뒤의 구조' 분석. 선정 이유를 spot_note에, 근거는 기준일 명시. ilabel='에디터의 결론'.
6. 지식(new_know): 커리큘럼 순서 — #008 인증(UL9540A·KC·CE), #009 계통 용어, #010 데이터센터 전력구조, 이후 심화 자유. 구조/숫자감각/왜 중요한가/실무 연결 + '오늘의 용어 3개' + 다음 강 예고. ilabel='실무 연결'.
7. 톤: 한국어, 간결·단정, 영업팀 발신 내부 리포트. 과장·투자 권유 금지.
8. 출력은 요구된 JSON 스키마만 — 다른 텍스트·마크다운 금지."""

# ── 에디터 지시서 v2 (신선도·중복 방지) — 2026-07-06 반영 ──────────
EDITOR_RULES = """

[에디터 지시서 v2 — 데일리 신문 원칙]
너는 인투알의 '아침신문 편집장'이다. 목표는 "어제 없던 이야기"로 채운 데일리.
직전 호에 실린 기사를 또 실으면 편집 실패다.

1) 신선도: 발행일 기준 72시간 이내 기사가 1순위(월요일판은 금~일 포함 96시간).
   카드 사용 기준 — 3일 이내 ◎ 최우선 / 4~7일 ○ 정상 / 8~14일 △ 부족할 때 보충 /
   15~45일 "참고" 태그 필수·최후 수단 / 45일 초과 절대 금지.
   신선한 기사가 부족하면 카드 수를 줄인다. 재탕으로 지면을 채우지 않는다.
2) 발행일(published) 확인이 안 되는 기사는 버린다. URL은 수집된 원문만 사용한다.
3) 중복 방지: 입력에 이미 걸러졌더라도, 같은 주제의 재등장은 '새 사실'(새 수치·새 발표·
   단계 진입)이 있을 때만 허용하고 "업데이트" 태그를 붙여 무엇이 새로운지 첫 요점에 쓴다.
   장기 이슈(예: 3차 입찰 대기, 23GW 물량)는 카드가 아니라 KPI·3줄 요약의 '상태 표시'로만
   유지하고, 상태가 변한 날에만 카드로 승격한다.
4) 지면: 3줄 요약 중 최소 2줄은 직전 호 이후 새로 확인된 소식으로 채운다.
   모든 요약·시사점은 외함·랙 제조사 관점을 유지한다.
5) 상세본문(detail): 모든 뉴스 카드와 new_spot에 보고서용 상세 해설을 detail 배열(문단 3~4개)로
   작성한다 — 배경→경과→수치→맥락→인투알 액션 순, 원문 전문 복제 금지(에디터 해설로 재구성).
6) 지면 총량 가드: 뉴스 카드는 3~5장(최대 5), detail 문단당 3~5문장, 불릿은 각 2문장 이내 —
   전체 출력은 반드시 한도 내에서 완결된 JSON이어야 한다."""

SYSTEM = SYSTEM + EDITOR_RULES


def _client():
    import anthropic
    return anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수 사용


def _call_once(prompt: str, max_tokens: int):
    print("[AI] 원고 집필 중", end="", flush=True)
    with _client().messages.stream(
        model=MODEL, max_tokens=max_tokens, system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as _s:
        for _i, _chunk in enumerate(_s.text_stream):
            if _i % 80 == 0:
                print(".", end="", flush=True)
        msg = _s.get_final_message()
    print(" 완료")
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
    return msg, text


def _call_json(prompt: str, max_tokens: int = 4096) -> dict:
    msg, text = _call_once(prompt, max_tokens)
    if getattr(msg, "stop_reason", None) == "max_tokens":
        print("[AI] 원고가 한도에 걸려 잘렸습니다 → 분량 30% 압축 지시로 1회 재시도(호출 비용 1회 추가)...")
        compact = (prompt + "\n\n[재시도 지침] 직전 출력이 길이 한도에 걸려 잘렸다. "
                   "카드는 최대 4장, detail은 카드당 3문단, 모든 문장을 간결하게 하여 "
                   "전체 분량을 30% 이상 압축하되 반드시 '완결된 JSON 하나'만 출력하라.")
        msg, text = _call_once(compact, max_tokens)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        from pathlib import Path
        Path("output").mkdir(exist_ok=True)
        Path("output/last_ai_response.txt").write_text(text, encoding="utf-8")
        if getattr(msg, "stop_reason", None) == "max_tokens":
            raise RuntimeError(
                "[AI] 압축 재시도에도 출력 한도에 걸렸습니다 — ai.py의 max_tokens를 올리거나 "
                "지면 분량 규정을 더 줄여야 합니다. 잘린 원고: output/last_ai_response.txt"
            ) from e
        raise RuntimeError(
            "[AI] 원고 형식(JSON)이 어긋났습니다 — 원본을 output/last_ai_response.txt 에 저장했습니다. "
            f"(파서 메시지: {e})"
        ) from e
    if getattr(msg, "stop_reason", None) == "max_tokens":
        raise RuntimeError("[AI] 출력이 한도에 정확히 도달했습니다(내용 누락 위험) — max_tokens 상향 필요")
    return data

def curate(articles: list[dict], max_per_section: int = 3) -> dict:
    """수집 기사 중 핵심을 선별해 섹션·카드 JSON 생성."""
    feed = json.dumps(articles[:80], ensure_ascii=False)
    prompt = f"""아래는 오늘 수집된 기사 목록(JSON)이다.

{feed}

이 중 인투알에 중요한 기사를 골라 아래 스키마의 JSON으로 출력하라.

{{
  "new_bids": <입찰·공고 관련 신규 감지 건수(정수)>,
  "sections": [
    {{"sec":"SEC 01","title":"정책 · 입찰 레이더","note":"전력거래소 · 기후에너지환경부 · 나라장터 모니터링","cards":[...]}},
    {{"sec":"SEC 02","title":"국내 업계 동향 — 배터리 · EPC · 발전사","note":"셀 3사 · 발전공기업 · EPC/SI","cards":[...]}},
    {{"sec":"SEC 03","title":"글로벌 동향 — 미국 · 중국 · 유럽","note":"Tesla · Fluence · CATL · Sungrow · BYD","cards":[...]}}
  ]
}}

card 스키마:
{{
  "accent": "bid|policy|kr|gl",   // 입찰·공고=bid, 정책=policy, 국내업계=kr, 글로벌=gl
  "tags": [{{"label":"<한글 2~6자>","cls":"t-bid|t-kr|t-gl|t-risk|"}}],  // 1~2개
  "title": "<헤드라인 재작성, 40자 내, 수치 포함>",
  "url": "<입력 목록의 url 그대로. 절대 새로 만들지 말 것>",
  "points": ["<핵심 요점 60자 내>", "...", "..."],  // 정확히 3개, 원문을 그대로 베끼지 말고 재서술
  "sources": [{{"name":"<매체명>","date":"'YY.MM.DD","url":"<입력 url 그대로>"}}],
  "insight": "<외함·랙 사업 관점 시사점 2문장, 핵심 구절 1곳만 <b></b>>",
  "impact": <1~4>, "impact_label": "낮음|중간|높음|매우 높음"
}}

규칙: 섹션당 최대 {max_per_section}개, 전체 6~9개. 입찰 공고·마감·낙찰은 최우선.
동일 사안 중복 금지. 확실하지 않은 수치는 쓰지 말 것.
최신성: 각 기사의 published(발행일)를 확인해 최근 것을 우선 선별하라.
2주 이상 지난 기사는 '지금도 유효한 큰 흐름(입찰 일정·정책 방향 등)'일 때만
넣고, 단순 지난 소식이면 제외하라. 날짜가 오래된 카드에는 tags에
{{"label":"참고","cls":"t-gl"}} 를 붙여 독자가 최신 뉴스와 구분할 수 있게 하라."""
    return _call_json(prompt, max_tokens=6000)


def overview(sections: dict, stock_names: list[str]) -> dict:
    """선별된 카드 기반으로 3줄 요약·To-Do·전략 코멘트·기업 이벤트 생성."""
    cards = json.dumps(sections, ensure_ascii=False)
    names = ", ".join(stock_names)
    prompt = f"""오늘 선별된 브리핑 카드는 다음과 같다.

{cards}

이를 바탕으로 아래 스키마의 JSON을 출력하라.

{{
  "summary3": [{{"lead":"<굵게 표시될 첫 문장>","rest":"<이어지는 설명 1~2문장>"}}, ...],  // 정확히 3개
  "todos": [{{"prio":"P1 긴급|P2 중요|P3 검토","cls":"p1|p2|p3","title":"<실행 항목>","desc":"<구체 실행 방법 1~2문장>","owner":"<담당/기한 예: 영업 / 이번 주>"}}, ...],  // 4~5개, P1부터
  "comment": "<대표이사용 전략 코멘트 4~5문장. 시장 구조 해석 + 인투알 액션 프레임. 핵심 구절 2~3곳 <b></b>>",
  "stock_events": {{"<기업명>":"<오늘 카드에서 해당 기업 관련 핵심 이벤트 1줄, 없으면 생략>"}}
}}

기업 목록: {names}
모든 내용은 카드에 근거하고, 외함·랙 제조사 실행 관점으로 쓸 것."""
    return _call_json(prompt, max_tokens=3000)


def daily_package(articles: list[dict], state_meta: dict, issue: dict) -> dict:
    """기사 후보 전체 → v3 지면 데이터 패키지(JSON) 생성."""
    import json as _json
    prompt = f"""오늘 발행 정보: {_json.dumps(issue, ensure_ascii=False)}
다음 지식 번호: #{state_meta.get('next_know', 8):03d} / 다음 스포트라이트 번호: #{state_meta.get('next_spot', 8):03d}

기사 후보(신선도·기출 필터 통과분):
{_json.dumps(articles[:40], ensure_ascii=False, indent=1)}

위 후보만 사용해 아래 JSON을 생성하라(스키마 외 텍스트 금지). 카드가 부족한 섹션은 cards를 빈 배열로 두고 note에 사유를 쓴다.
{{
 "mast": {{"counts": "수집 N건 → ... 카드 n · 단신 m (사유)", "notice": "신규 입찰·공고 상태 한 줄"}},
 "three_lines": [{{"head": "...", "body": "..."}} x3],
 "kpis": [{{"label": "...", "value": "...", "small": "", "note": "▲/— ...", "dir": "up|flat"}} x4],
 "news_sections": [{{"sec": "SEC 01", "title": "정책 · 입찰 레이더", "note": "...", "cards": [{{"cls": "policy|kr|gl", "tags": [{{"t": "...", "cls": "t-bid|t-kr|t-gl|"}}], "url": "...", "title": "...", "bullets": ["..."], "srcs": [{{"n": "매체 'YY.MM.DD", "u": "..."}}], "insight": "...", "impact_n": 1-4, "impact_val": "n/4 ...", "detail": ["상세 해설 문단1", "문단2", "문단3"]}}]}}, {{"sec": "SEC 02", ...}}, {{"sec": "SEC 03", ...}}],
 "briefs": [{{"cat": "...", "txt": "...", "name": "매체 M/D", "url": "..."}}],
 "radar_note": "레이더: 지표① ... — ...",
 "todos": [{{"prio": "P1 긴급", "cls": "p1", "title": "...", "body": "...", "owner": "... / ..."}} 4~6개],
 "comment": "전략 코멘트 문단",
 "spot_note": "최근 3개 롤링(전문 그대로 · 새 글 왼쪽) — #NNN 선정 이유: ...",
 "new_spot": {{"no": {state_meta.get('next_spot', 8)}, "tags": [...], "url": "근거 URL", "title": "...", "bullets": [...], "srcs": [...], "src_tail": "— 분석 코너는 신선도 창 대신 기준일 명시", "insight": "...", "impact_n": 3, "impact_val": "3/4 ...", "detail": ["상세 해설 문단1", "문단2", "문단3"]}},
 "new_know": {{"no": {state_meta.get('next_know', 8)}, "title": "...", "bullets": [구조/숫자/실무 4개], "srcs": [...], "src_tail": "· <b>다음 강 예고 — #{state_meta.get('next_know', 8)+1:03d} ...</b>", "insight": "실무 연결 — ... <b>오늘의 용어 3개</b>: ..."}}
}}"""
    return _call_json(prompt, max_tokens=30000)
