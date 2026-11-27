"""AI 모듈 — Claude API로 기사 선별·요약·시사점·To-Do 생성.

2026-11 개편:
  - 섹션 4개(정책·입찰 / 국내 / 글로벌 ESS / 데이터센터·AI 전력), 섹션별 카드 상한.
  - 기사 주소를 주고받지 않고 번호(K01·G03·D02)로 지목 → 코드가 실제 주소로 바꿔 넣는다.
    (목록에 없는 번호·주소는 링크를 빼 버린다 — 지어낸 주소가 지면에 실릴 수 없다.)
  - 호출별 토큰 사용량을 USAGE에 남긴다(실행 기록·리허설 진단용).
  - 모델은 config.yaml의 ai.model이 우선이고, GitHub Secret(CLAUDE_MODEL)의 모델은 예비다.
    우선 모델 호출이 거절되면(없는 이름·권한 없음) 예비 모델로 바꿔 발행을 이어 간다.
"""
from __future__ import annotations
import json
import os
import re

DEFAULT_MODEL = "claude-sonnet-5-5"
MODEL = os.environ.get("CLAUDE_MODEL") or DEFAULT_MODEL
FALLBACK_MODEL = ""     # 우선 모델이 거절됐을 때 쓸 예비 모델
MODEL_NOTE = ""         # 예비 모델로 바꿨다면 그 사유
USAGE: list[dict] = []  # 이번 실행의 호출 기록


def configure(cfg: dict | None) -> None:
    """모델 정하기 — config.yaml의 ai.model이 있으면 그것을 쓰고, Secret(CLAUDE_MODEL)의 모델은 예비로 둔다."""
    global MODEL, FALLBACK_MODEL, MODEL_NOTE
    env_model = (os.environ.get("CLAUDE_MODEL") or "").strip()
    want = str(((cfg or {}).get("ai") or {}).get("model") or "").strip()
    MODEL_NOTE = ""
    if want:
        MODEL = want
        FALLBACK_MODEL = env_model if env_model and env_model != want else (DEFAULT_MODEL if want != DEFAULT_MODEL else "")
    else:
        MODEL, FALLBACK_MODEL = env_model or DEFAULT_MODEL, ""

SECTIONS = [  # (코드, 제목, 기본 카드 색, 상한 설정 키, 기본 상한)
    ("SEC 01", "정책 · 입찰 레이더", "policy", "policy", 2),
    ("SEC 02", "국내 산업 동향", "kr", "kr", 2),
    ("SEC 03", "글로벌 ESS", "gl", "global", 4),
    ("SEC 04", "데이터센터 · AI 전력", "dc", "datacenter", 2),
]

SYSTEM = """당신은 '인투알'(2차전지 ESS 외함·컨테이너·랙·IDC 컨테이너 제조사) 영업팀의 데일리 브리핑 에디터다. 규칙(v11 요약):
1. 사실만: 입력으로 받은 기사에 없는 사실·숫자·시세를 절대 지어내지 않는다.
2. 기사 지목은 번호로만: url 과 srcs의 u 자리에는 입력 기사의 id(예: K01, G03, D02, N01)를 그대로 적는다. 주소를 직접 쓰지 않는다.
3. 재탕 금지: 입력 기사는 이미 기출·신선도 필터를 통과했다. 카드마다 발행일을 표기한다.
4. 카드: 불릿 2~4개(핵심 숫자 <b> 강조), '인투알 시사점'(외함·랙·컨테이너 관점 필수), 영향도 1~4, detail(보고서용 상세 해설 3문단 — 배경·경과·숫자 분해·인투알 액션. 원문 전재 금지, 해설로 작성).
5. 지면 구성: 섹션별 카드 상한을 지킨다. 재료가 부족하면 지어내지 말고 카드를 줄이고 mast.counts에 사유를 쓴다.
6. 스포트라이트(new_spot): 매일 1건 자율 선정 — 뉴스 재탕이 아닌 '숫자 뒤의 구조' 분석. 근거는 기준일 명시. ilabel='에디터의 결론'.
7. 지식(new_know): 지난 번호에 이어지는 심화 과정. 구조/숫자감각/왜 중요한가/실무 연결 + '오늘의 용어 3개' + 다음 강 예고. ilabel='실무 연결'.
8. 톤: 한국어, 간결·단정, 영업팀 발신 내부 리포트. 과장·투자 권유 금지. 영어 기사는 한국어로 풀어 쓰되 고유명사·수치는 원문 그대로.
9. 출력은 요구된 JSON 스키마만 — 다른 텍스트·마크다운 금지."""

EDITOR_RULES = """

[에디터 지시서 — 데일리 신문 원칙]
너는 인투알의 '아침신문 편집장'이다. 목표는 "어제 없던 이야기"로 채운 데일리.
직전 호에 실린 기사를 또 실으면 편집 실패다.

1) 신선도: 발행일 기준 72시간 이내 기사가 1순위(월요일판은 금~일 포함 96시간).
   카드 사용 기준 — 3일 이내 ◎ 최우선 / 4~7일 ○ 정상 / 8~14일 △ 부족할 때 보충 /
   15~45일 "참고" 태그 필수·최후 수단 / 45일 초과 절대 금지.
   신선한 기사가 부족하면 카드 수를 줄인다. 재탕으로 지면을 채우지 않는다.
2) 발행일(published) 확인이 안 되는 기사는 버린다(전력거래소 공지 N번은 예외).
3) 중복 방지: 같은 주제의 재등장은 '새 사실'(새 수치·새 발표·단계 진입)이 있을 때만 허용하고
   "업데이트" 태그를 붙여 무엇이 새로운지 첫 요점에 쓴다. 같은 사안을 다룬 기사가 여러 건이면
   카드 1장으로 묶고 srcs에 함께 적는다. 장기 이슈는 KPI·3줄 요약의 '상태 표시'로만 유지하고,
   상태가 변한 날에만 카드로 승격한다.
4) 지면: 3줄 요약 중 최소 2줄은 직전 호 이후 새로 확인된 소식으로 채운다.
   모든 요약·시사점은 외함·랙·컨테이너 제조사 관점을 유지한다.
5) 섹션 배정:
   - SEC 01 정책·입찰 레이더: 국내 정책·제도·입찰·공고·안전규제.
   - SEC 02 국내 산업 동향: 국내 기업·프로젝트·수주·실적.
   - SEC 03 글로벌 ESS: 해외 시장·프로젝트·수주·제도·사고. global 묶음(해외 매체 원문)을 우선하고,
     지역(북미·유럽·중국·인도·호주·중동 등)과 주제가 겹치지 않게 고른다.
   - SEC 04 데이터센터·AI 전력: 데이터센터의 전력 수급, 전원·UPS·배터리·ESS, 모듈형·컨테이너형
     데이터센터, 전력망 접속·요금 제도. 전력·인프라 접점이 없는 AI 서비스·반도체 소식은 싣지 않는다.
     시사점은 IDC 컨테이너·전원 모듈·배터리 인클로저 관점으로 쓴다.
6) 상세본문(detail): 모든 뉴스 카드와 new_spot에 detail 배열(문단 3개, 문단당 2~4문장)을 쓴다 —
   배경→경과·수치→인투알 액션 순, 원문 전문 복제 금지(에디터 해설로 재구성).
7) 분량 가드: 불릿은 각 2문장 이내. 전체 출력은 반드시 한도 내에서 완결된 JSON이어야 한다."""

SYSTEM = SYSTEM + EDITOR_RULES


def _client():
    import anthropic
    return anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수 사용


def _stream(model: str, prompt: str, max_tokens: int, system: str | None):
    with _client().messages.stream(
        model=model, max_tokens=max_tokens, system=system or SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as _s:
        for _i, _chunk in enumerate(_s.text_stream):
            if _i % 80 == 0:
                print(".", end="", flush=True)
        return _s.get_final_message()


def _call_once(prompt: str, max_tokens: int, system: str | None = None, label: str = "원고 집필"):
    global MODEL, MODEL_NOTE
    print(f"[AI] {label} 중({MODEL})", end="", flush=True)
    try:
        msg = _stream(MODEL, prompt, max_tokens, system)
    except Exception as exc:
        # 모델 자체가 거절된 경우(400 잘못된 요청 · 403 권한 없음 · 404 없는 모델)에만 예비 모델로 한 번 더 시도한다
        status = getattr(exc, "status_code", None)
        if status not in (400, 403, 404) or not FALLBACK_MODEL or FALLBACK_MODEL == MODEL:
            raise
        MODEL_NOTE = f"{MODEL} 호출 거절(HTTP {status}) → {FALLBACK_MODEL}(으)로 전환"
        print(f"\n[AI] {MODEL_NOTE}: {str(exc)[:160]}")
        MODEL = FALLBACK_MODEL
        print(f"[AI] {label} 중({MODEL})", end="", flush=True)
        msg = _stream(MODEL, prompt, max_tokens, system)
    print(" 완료")
    try:
        u = msg.usage
        USAGE.append({"label": label, "in": int(getattr(u, "input_tokens", 0) or 0),
                      "out": int(getattr(u, "output_tokens", 0) or 0), "stop": getattr(msg, "stop_reason", "")})
    except Exception:
        pass
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
    return msg, text


def _call_json(prompt: str, max_tokens: int = 4096, system: str | None = None, label: str = "원고 집필",
               retry_hint: str | None = None) -> dict:
    msg, text = _call_once(prompt, max_tokens, system, label)
    if getattr(msg, "stop_reason", None) == "max_tokens":
        print("[AI] 원고가 한도에 걸려 잘렸습니다 → 분량 압축 지시로 1회 재시도(호출 비용 1회 추가)...")
        compact = (prompt + "\n\n[재시도 지침] 직전 출력이 길이 한도에 걸려 잘렸다. "
                   + (retry_hint or "모든 문장을 간결하게 하여 전체 분량을 30% 이상 압축하되 ")
                   + "반드시 '완결된 JSON 하나'만 출력하라.")
        msg, text = _call_once(compact, max_tokens, system, label + "(압축 재시도)")
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


# ───────────────────────── 번호 → 주소, 규격 정리 ─────────────────────────
def resolve_ids(pkg, table: dict) -> dict:
    """원고 안의 기사 번호(K01…)를 실제 주소로 바꾼다. 목록에 없는 번호·주소는 링크를 뺀다."""
    known = {a.get("url") for a in table.values() if a.get("url")}
    stats = {"by_id": 0, "by_url": 0, "dropped": 0}

    def fix(v):
        if not isinstance(v, str) or not v.strip():
            return ""
        key = v.strip().strip("<>[]#").upper()
        if key in table:
            stats["by_id"] += 1
            return table[key].get("url", "")
        if v.strip() in known:
            stats["by_url"] += 1
            return v.strip()
        m = re.search(r"\b([KGDN]\d{2})\b", key)  # "K01, K02"처럼 여러 개를 적었으면 첫 번호
        if m and m.group(1) in table:
            stats["by_id"] += 1
            return table[m.group(1)].get("url", "")
        stats["dropped"] += 1
        return ""

    def walk(o):
        if isinstance(o, dict):
            for k, v in list(o.items()):
                if k in ("url", "u"):
                    o[k] = fix(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(pkg)
    return stats


def strip_label(text: str, label: str) -> str:
    """시사점 글머리에 머리말('인투알 시사점 —' 등)이 또 들어 있으면 뗀다 — 지면이 머리말을 따로 붙이기 때문."""
    return re.sub(rf"^\s*(?:<b>)?\s*{re.escape(label)}\s*(?:</b>)?\s*[—–:-]\s*", "", text or "").strip()


def _as_list(v) -> list:
    if isinstance(v, list):
        return v
    return [v] if v else []


def _clean_card(c: dict, default_cls: str) -> dict | None:
    if not isinstance(c, dict) or not str(c.get("title", "")).strip():
        return None
    try:
        n = max(1, min(4, int(c.get("impact_n", 2))))
    except (TypeError, ValueError):
        n = 2
    tags = [{"t": str(t.get("t", "")).strip(), "cls": str(t.get("cls", "") or "")}
            for t in _as_list(c.get("tags")) if isinstance(t, dict) and str(t.get("t", "")).strip()][:3]
    srcs = [{"n": str(s.get("n", "")).strip(), "u": s.get("u", "") or ""}
            for s in _as_list(c.get("srcs")) if isinstance(s, dict) and str(s.get("n", "")).strip()][:4]
    cls = c.get("cls") if c.get("cls") in ("policy", "kr", "gl", "dc", "bid") else default_cls
    return {
        "cls": cls, "tags": tags, "url": c.get("url", "") or "", "title": str(c["title"]).strip(),
        "bullets": [str(b) for b in _as_list(c.get("bullets")) if str(b).strip()][:4],
        "srcs": srcs, "insight": strip_label(str(c.get("insight", "")), "인투알 시사점"),
        "impact_n": n, "impact_val": str(c.get("impact_val") or f"{n}/4").strip(),
        "detail": [str(p) for p in _as_list(c.get("detail")) if str(p).strip()][:4],
    }


def normalize(pkg: dict, caps: dict | None = None) -> dict:
    """원고를 지면 규격에 맞춘다 — 섹션 4개 고정, 섹션별 상한, To-Do 3건. 빠진 칸은 기본값."""
    caps = caps or {}
    given = [s for s in _as_list(pkg.get("news_sections")) if isinstance(s, dict)]
    by_code = {str(s.get("sec", "")).strip().upper(): s for s in given}
    out = []
    for i, (code, title, cls, cap_key, cap_default) in enumerate(SECTIONS):
        src = by_code.get(code) or (given[i] if i < len(given) and not by_code else {})
        cap = int(caps.get(cap_key, cap_default))
        cards = [x for x in (_clean_card(c, cls) for c in _as_list(src.get("cards"))) if x][:cap]
        if cap_key == "datacenter":
            for c in cards:
                c["cls"] = "dc"
        note = str(src.get("note", "") or "").strip() or ("" if cards else "오늘은 실을 만한 새 기사가 없습니다")
        out.append({"sec": code, "title": title, "note": note, "cards": cards})
    pkg["news_sections"] = out
    pkg["three_lines"] = [l for l in _as_list(pkg.get("three_lines")) if isinstance(l, dict)][:3]
    pkg["kpis"] = [k for k in _as_list(pkg.get("kpis")) if isinstance(k, dict)][:4]
    pkg["briefs"] = [b for b in _as_list(pkg.get("briefs")) if isinstance(b, dict) and str(b.get("txt", "")).strip()][:int(caps.get("briefs", 8))]
    pkg["todos"] = [t for t in _as_list(pkg.get("todos")) if isinstance(t, dict) and str(t.get("title", "")).strip()][:int(caps.get("todos", 3))]
    if not isinstance(pkg.get("mast"), dict):
        pkg["mast"] = {}
    pkg.setdefault("radar_note", "")
    pkg.setdefault("comment", "")
    return pkg


def daily_package(payload: dict, state_meta: dict, issue: dict, caps: dict | None = None) -> dict:
    """묶음별 기사 후보 → 지면 데이터 패키지(JSON). payload는 collectors.select_candidates()의 결과."""
    caps = caps or {}
    cap = {key: int(caps.get(key, d)) for _, _, _, key, d in SECTIONS}
    n_briefs = int(caps.get("briefs", 8))
    n_spot, n_know = state_meta.get("next_spot", 8), state_meta.get("next_know", 8)
    counts = {k: len(v) for k, v in payload.items()}
    card = ('{"cls": "policy|kr|gl|dc", "tags": [{"t": "...", "cls": "t-bid|t-kr|t-gl|"}], "url": "<기사 id>", "title": "...", '
            '"bullets": ["..."], "srcs": [{"n": "매체 \'YY.MM.DD", "u": "<기사 id>"}], "insight": "...", '
            '"impact_n": 1-4, "impact_val": "n/4 ...", "detail": ["문단1", "문단2", "문단3"]}')
    prompt = f"""오늘 발행 정보: {json.dumps(issue, ensure_ascii=False)}
다음 지식 번호: #{n_know:03d} / 다음 스포트라이트 번호: #{n_spot:03d}

기사 후보(신선도·기출 필터 통과분) — 묶음별 건수 {json.dumps(counts, ensure_ascii=False)}:
kr = 국내 매체 / global = 해외 매체(영어 원문) / datacenter = 데이터센터·AI 전력 / notices = 전력거래소 공지
{json.dumps(payload, ensure_ascii=False, indent=1)}

위 후보만 사용해 아래 JSON을 생성하라(스키마 외 텍스트 금지).
섹션별 카드 상한: SEC 01 최대 {cap['policy']}장 · SEC 02 최대 {cap['kr']}장 · SEC 03 최대 {cap['global']}장 · SEC 04 최대 {cap['datacenter']}장.
쓸 만한 기사가 있으면 상한까지 채우고, 없으면 cards를 빈 배열로 두고 note에 사유를 쓴다. 단신은 5~{n_briefs}건(카드로 쓰지 않은 기사, 해외·데이터센터 포함).
url·u 자리에는 반드시 위 후보의 id만 적는다.
{{
 "mast": {{"counts": "수집 N건 → ... 카드 n(정책 a · 국내 b · 글로벌 c · 데이터센터 d) · 단신 m (사유)", "notice": "신규 입찰·공고 상태 한 줄"}},
 "three_lines": [{{"head": "...", "body": "..."}} x3],
 "kpis": [{{"label": "...", "value": "...", "small": "", "note": "▲/— ...", "dir": "up|flat"}} x4],
 "news_sections": [
  {{"sec": "SEC 01", "note": "오늘 이 섹션의 한 줄 요지", "cards": [{card}]}},
  {{"sec": "SEC 02", "note": "...", "cards": [...]}},
  {{"sec": "SEC 03", "note": "...", "cards": [...]}},
  {{"sec": "SEC 04", "note": "...", "cards": [...]}}
 ],
 "briefs": [{{"cat": "기업|정책|시장|글로벌|데이터센터 등", "txt": "...", "name": "매체 M/D", "url": "<기사 id>"}}],
 "radar_note": "레이더: 지표① ... — ...",
 "todos": [{{"prio": "P1 긴급|P2 중요|P3 검토", "cls": "p1|p2|p3", "title": "...", "body": "...", "owner": "... / ..."}} 정확히 3개, 우선순위 순],
 "comment": "전략 코멘트 문단",
 "new_spot": {{"no": {n_spot}, "tags": [...], "url": "<근거 기사 id>", "title": "...", "bullets": [...], "srcs": [...], "src_tail": "— 분석 코너는 신선도 창 대신 기준일 명시", "insight": "...", "impact_n": 3, "impact_val": "3/4 ...", "detail": ["문단1", "문단2", "문단3"]}},
 "new_know": {{"no": {n_know}, "title": "...", "bullets": [구조/숫자/실무 4개], "srcs": [...], "src_tail": "· <b>다음 강 예고 — #{n_know + 1:03d} ...</b>", "insight": "... <b>오늘의 용어 3개</b>: ..."}}
}}"""
    hint = ("detail은 카드당 2문단·문단당 2문장으로 줄이고, SEC 03은 최대 3장·SEC 04는 최대 1장으로 하여 "
            "전체 분량을 30% 이상 압축하되 ")
    # 한도는 넉넉히 — 생각(thinking) 토큰도 이 한도에 포함된다. 과금은 실제 쓴 만큼만 된다.
    return _call_json(prompt, max_tokens=48000, label="지면 원고 집필", retry_hint=hint)
