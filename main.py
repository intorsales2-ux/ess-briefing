"""인투알 ESS 데일리 브리핑 — 파이프라인 오케스트레이터.

사용법:
  python main.py                       # 실제 발행: 수집 → AI 편집 → 렌더링 → 이메일 발송
  python main.py --rehearsal           # 리허설: 독자에게 보내지 않고 미리보기(output/preview.html)만 만든다
  python main.py --rehearsal --date 2026-11-30   # 그 날짜인 것처럼 리허설(요일 코너·계절 장식·안내 확인용)
  python main.py --dry-run             # API 키 없이 샘플 데이터로 렌더링
  python main.py --no-email            # 이메일 발송 생략
GitHub Actions에서는 환경변수로 같은 일을 한다: BRIEFING_MODE=rehearsal, BRIEFING_DATE=YYYY-MM-DD
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

import render

BASE = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]
RUN_LOG = BASE / "output" / "run_log.json"


def load_config() -> dict:
    return yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))


def publish_time(cfg: dict) -> str:
    """지면·메일에 적는 발행 시각 표기(예: 07:00). 설정이 없거나 형식이 이상하면 07:00."""
    t = str((cfg or {}).get("publish_time", "") or "").strip()
    return t if len(t) == 5 and t[2] == ":" and t.replace(":", "").isdigit() else "07:00"


def _issue_fields(now: datetime, cfg: dict | None = None) -> dict:
    nxt = now + timedelta(days=1)
    while nxt.weekday() >= 5:  # 주말 건너뛰기
        nxt += timedelta(days=1)
    return {
        "issue_no": f"제{now.year}-{now.timetuple().tm_yday:03d}호",
        "date_str": now.strftime(f"%Y.%m.%d({WEEKDAY_KO[now.weekday()]}) %H:%M KST"),
        "date_short": now.strftime("%Y.%m.%d"),
        "next_issue": nxt.strftime(f"%m.%d({WEEKDAY_KO[nxt.weekday()]}) ") + publish_time(cfg),
    }


def pick_notice(cfg: dict, state: dict, today: str) -> dict | None:
    """오늘 띄울 안내(개편 안내 등). 안내마다 한 번, 처음 발행되는 날 하루만 표시한다.

    config.yaml 의 notices 목록에서 아직 내보내지 않은 첫 안내를 고른다.
    not_before(이 날짜 전에는 숨김) · not_after(이 날짜가 지나면 폐기)를 지킨다.
    """
    shown = state.get("notices_shown", {}) or {}
    for n in cfg.get("notices", []) or []:
        nid, title = str(n.get("id", "")).strip(), str(n.get("title", "")).strip()
        if not nid or not title:
            continue
        if str(n.get("not_before") or "") > today:
            continue
        if n.get("not_after") and str(n["not_after"]) < today:
            continue
        if nid in shown and shown[nid] != today:  # 이미 다른 날 내보냄
            continue
        return {"id": nid, "title": title, "lead": str(n.get("lead", "") or ""),
                "points": [str(x) for x in (n.get("items") or [])]}
    return None


def apply_dressing(data: dict, cfg: dict, state: dict, now: datetime) -> None:
    """계절 장식과 안내 — 날짜만으로 정해지는 꾸밈."""
    import seasons
    theme = seasons.pick(now.date(), str(cfg.get("season", "auto")))
    data["_season"] = theme
    data["season_html"] = seasons.banner_html(theme)
    data["notice"] = pick_notice(cfg, state, now.strftime("%Y-%m-%d"))


def build_dry_run_data(now: datetime, cfg: dict) -> dict:
    """샘플 데이터로 디자인·발송 흐름 점검 — API 키 없이 동작, 상태 저장 안 함."""
    data = json.loads((BASE / "data" / "sample_data.json").read_text(encoding="utf-8"))
    data.pop("comments_api_url", None)
    data["_dry"] = True
    data["site_url"] = cfg.get("site_url", "")
    apply_dressing(data, cfg, render._load_state(), now)
    return data


def build_live_data(cfg: dict, now: datetime, run: dict, rehearsal: bool = False, real_now: datetime | None = None) -> dict:
    import ai
    import collectors
    import dedup
    import weekly

    ai.configure(cfg)
    if now.weekday() == 0:
        cfg["news"]["lookback_hours"] = max(cfg["news"]["lookback_hours"], 96)
        print("[main] 월요일 → 수집창 96시간(금~일 포함)으로 확장")

    print("[main] 1/5 뉴스·공고 수집 중...")
    articles = collectors.collect_news(cfg) + collectors.collect_kpx_notices(cfg)
    n_all = len(articles)
    articles, n_dup = dedup.filter_new(articles, dedup.load_seen())
    payload, table = collectors.select_candidates(articles, cfg)
    run["collected"] = {b: sum(1 for a in articles if a.get("bucket") == b) for b in ("kr", "global", "datacenter", "notice")}
    run["candidates"] = {k: len(v) for k, v in payload.items()}
    run["feeds"] = collectors.diag_lines()
    print(f"[main]   수집 {n_all}건 → 기출 {n_dup}건 제외 → 남은 {len(articles)}건 "
          f"(국내 {run['collected']['kr']} · 해외 {run['collected']['global']} · 데이터센터 {run['collected']['datacenter']})")
    print(f"[main]   편집 후보: 국내 {run['candidates'].get('kr', 0)} · 해외 {run['candidates'].get('global', 0)} · "
          f"데이터센터 {run['candidates'].get('datacenter', 0)} · 공지 {run['candidates'].get('notices', 0)}")

    print("[main] 2/5 Claude 편집 중...")
    state = render._load_state()
    issue = _issue_fields(now, cfg)
    caps = (cfg.get("report", {}) or {}).get("caps", {}) or {}
    pkg = ai.daily_package(payload, {"next_spot": state.get("next_spot", 1), "next_know": state.get("next_know", 1)}, issue, caps)
    run["links"] = ai.resolve_ids(pkg, table)
    pkg = ai.normalize(pkg, caps)

    data = dict(pkg)
    data.update(issue)
    data["mast"].setdefault("range", f"직전 발행 이후 ~ {now:%m.%d %H:%M}")
    data.setdefault("calendar", None)
    data["_dry"] = False
    data["site_url"] = cfg.get("site_url", "")
    run["cards"] = {s["sec"]: len(s["cards"]) for s in data["news_sections"]}
    run["briefs"] = len(data.get("briefs", []))

    print("[main] 3/5 환율·주간 코너...")
    if (cfg.get("fx", {}) or {}).get("enabled", True):
        try:
            import fx
            data["fx"] = fx.fetch()
        except Exception as e:  # 환율은 부가 정보 — 실패해도 발행은 계속
            print(f"[main] 환율 건너뜀({type(e).__name__}: {e})")
            data["fx"] = None
    run["fx"] = bool(data.get("fx"))

    def _corner(fn, *a):  # 주간 코너는 부가 — 실패하면 그 코너만 생략
        try:
            return fn(*a)
        except Exception as e:
            print(f"[main] 주간 코너 건너뜀({type(e).__name__}: {e})")
            return None

    parts = []
    if (cfg.get("weekly", {}) or {}).get("enabled", True):
        if rehearsal:  # 리허설은 두 코너를 한 번에 시험한다(퀴즈는 실제 이번 주 지면으로 출제)
            parts = [_corner(weekly.make_class, state, now, ai._call_json),
                     _corner(weekly.make_quiz, real_now or now, data, data["site_url"], ai._call_json)]
        elif now.weekday() == 4:  # 금요일 — 주간 퀴즈
            parts = [_corner(weekly.make_quiz, now, data, data["site_url"], ai._call_json)]
        elif now.weekday() <= 3 and weekly.class_due(state, now):  # 그 주의 첫 호(보통 월요일) — AI 활용 교실
            parts = [_corner(weekly.make_class, state, now, ai._call_json)]
    parts = [p for p in parts if p]
    if parts:
        data["weekly_html"] = "\n".join(p["html"] for p in parts)
        data["weekly_note"] = ("리허설 — 월요일 코너(AI 활용 교실)와 금요일 코너(주간 퀴즈)를 함께 표시합니다" if rehearsal
                               else "매주 월요일 — AI 활용 교실" if parts[0]["kind"] == "class" else "매주 금요일 — 한 주 지면 돌아보기")
        data["_weekly"] = parts[0]
    run["weekly"] = " + ".join(p["label"] for p in parts)

    apply_dressing(data, cfg, state, now)
    run["season"] = (data.get("_season") or {}).get("key", "")
    run["notice"] = (data.get("notice") or {}).get("id", "")
    run["model"] = ai.MODEL
    run["model_note"] = ai.MODEL_NOTE
    run["usage"] = ai.USAGE
    return data


def save_state_extras(data: dict, today: str) -> None:
    """발행 성공 뒤 — 주간 코너 진도와 '안내 내보냄' 표시를 상태 파일에 적는다."""
    state = render._load_state()
    wk = data.get("_weekly")
    if wk and wk.get("state"):
        state.update(wk["state"])
    if data.get("notice"):
        state.setdefault("notices_shown", {})[data["notice"]["id"]] = today
    render.STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def write_run_log(run: dict) -> None:
    try:
        log = json.loads(RUN_LOG.read_text(encoding="utf-8")) if RUN_LOG.exists() else []
    except Exception:
        log = []
    log.append({k: v for k, v in run.items() if k != "feeds"})
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    RUN_LOG.write_text(json.dumps(log[-90:], ensure_ascii=False, indent=1), encoding="utf-8")


def write_diag(run: dict, path: Path) -> None:
    """리허설 진단 — 무엇이 어떻게 돌았는지 사람이 읽는 글로 남긴다(비밀값은 적지 않는다)."""
    u = run.get("usage", [])
    lines = [
        "인투알 ESS 데일리 브리핑 — 리허설 진단",
        f"실행: {run.get('date')} {run.get('started')} ~ {run.get('finished')} KST · 지면 기준 날짜 {run.get('issue_date')}",
        f"결과: {'성공' if run.get('ok') else '실패 — ' + str(run.get('error', ''))}",
        f"모델: {run.get('model', '')}" + (f"  ※ {run['model_note']}" if run.get("model_note") else ""),
        f"수집(기출 제외 후): {run.get('collected', {})}",
        f"편집 후보: {run.get('candidates', {})}",
        f"카드: {run.get('cards', {})} · 단신 {run.get('briefs', 0)}",
        f"기사 링크: {run.get('links', {})}  (by_id=번호로 지목, dropped=목록에 없어 링크 제거)",
        f"환율: {'표시' if run.get('fx') else '생략(수신 실패)'} · 주간 코너: {run.get('weekly') or '없음'} · 계절: {run.get('season') or '없음'} · 안내: {run.get('notice') or '없음'}",
        f"메일: {run.get('mail', '')}",
        "토큰: " + (" / ".join(f"{x.get('label')}: 입력 {x.get('in')} · 출력 {x.get('out')}" for x in u) or "기록 없음"),
        "", "[수집 창구별 결과]",
    ] + list(run.get("feeds", []))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="인투알 ESS 데일리 브리핑 파이프라인")
    ap.add_argument("--dry-run", action="store_true", help="샘플 데이터로 렌더링만 수행")
    ap.add_argument("--no-email", action="store_true", help="이메일 발송 생략")
    ap.add_argument("--rehearsal", action="store_true", help="리허설 — 독자에게 보내지 않고 미리보기만")
    ap.add_argument("--date", default="", help="리허설 기준 날짜(YYYY-MM-DD)")
    args = ap.parse_args()

    try:  # .env 지원(선택)
        from dotenv import load_dotenv
        load_dotenv(BASE / ".env")
    except ImportError:
        pass

    cfg = load_config()
    started = datetime.now(KST)
    now = started
    rehearsal = args.rehearsal or os.environ.get("BRIEFING_MODE", "").strip().lower() == "rehearsal"
    want_date = (args.date or os.environ.get("BRIEFING_DATE", "")).strip()
    if want_date:
        if rehearsal or args.dry_run:
            try:
                d = datetime.strptime(want_date, "%Y-%m-%d")
                now = started.replace(year=d.year, month=d.month, day=d.day)
                print(f"[main] 리허설 기준 날짜 {want_date}({WEEKDAY_KO[now.weekday()]})로 진행합니다.")
            except ValueError:
                print(f"[main] 날짜 형식이 맞지 않아 무시합니다: {want_date!r} (예: 2026-11-30)")
        else:
            print("[main] 날짜 지정은 리허설에서만 쓸 수 있어 무시합니다(실제 발행은 항상 오늘 날짜).")
    today = now.strftime("%Y-%m-%d")

    if args.dry_run or not os.environ.get("ANTHROPIC_API_KEY"):
        if not args.dry_run:
            print("[main] ANTHROPIC_API_KEY 없음 → dry-run 모드로 전환")
        mode = "dry-run"
    else:
        mode = "rehearsal" if rehearsal else "live"
    run = {"date": started.strftime("%Y-%m-%d"), "issue_date": today, "mode": mode,
           "event": os.environ.get("GH_EVENT", ""), "schedule": os.environ.get("GH_SCHEDULE", ""),
           "started": started.strftime("%H:%M:%S"), "ok": False}
    out_dir = BASE / cfg.get("output", {}).get("dir", "output")
    try:
        data = (build_dry_run_data(now, cfg) if mode == "dry-run"
                else build_live_data(cfg, now, run, rehearsal=(mode == "rehearsal"), real_now=started))
        if mode == "rehearsal":
            data["_nosave"] = True
            data["rehearsal"] = (f"실행 {started:%Y.%m.%d %H:%M} KST · 지면 기준 날짜 "
                                 f"{now:%Y.%m.%d}({WEEKDAY_KO[now.weekday()]})")

        print("[main] 4/5 렌더링 중...")
        out_path = render.render_to_file(data, out_dir / ("preview.html" if mode == "rehearsal" else "index.html"))
        archive = mode != "rehearsal" and cfg.get("output", {}).get("archive", True)
        if archive:
            arch = out_dir / "archive" / f"{today}.html"
            arch.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(out_path, arch)
        print(f"[main] 완료({mode}) → {out_path}")

        # 시세 자동 기입 — 실패해도 발행은 계속(보드는 '—' 유지)
        try:
            import stock_board
            print("[main] 주가 보드 기입 중 (야후 확정 종가)...")
            stock_board.fill(str(out_path))
            if archive:
                shutil.copy(out_path, arch)  # 숫자 기입본으로 아카이브 갱신
        except Exception as e:
            print(f"[main] 시세 기입 건너뜀({type(e).__name__}: {e}) — 보드는 '—' 상태로 발행됩니다.")

        if mode == "live":  # 발행 성공 → 기출 목록·주간 코너 진도·안내 표시 갱신
            import dedup
            urls = [c.get("url") for s in data.get("news_sections", []) for c in s.get("cards", []) if c.get("url")]
            urls += [b.get("url") for b in data.get("briefs", []) if b.get("url")]
            dedup.record(urls, dedup.load_seen())
            print(f"[main] 기출 목록 갱신 → output/seen_urls.json (+{len(urls)}건)")
            save_state_extras(data, today)

        print("[main] 5/5 메일...")
        if not args.no_email and mode in ("live", "rehearsal") and cfg.get("email", {}).get("enabled", True):
            import emailer
            subject = f"{cfg['email'].get('subject_prefix', '[인투알] ESS 데일리 브리핑')} {now:%m/%d}"
            summary = "\n".join(f"{i+1}. {l['head']} {l['body']}" for i, l in enumerate(data.get("three_lines", [])))
            extras = {"season": data.get("_season"), "notice": data.get("notice"),
                      "weekly": (data.get("_weekly") or {}).get("label", ""), "rehearsal": mode == "rehearsal",
                      "publish_time": publish_time(cfg)}
            run["mail"] = emailer.send_briefing(out_path.read_text(encoding="utf-8"), subject, summary,
                                                site_url=data.get("site_url", ""), extras=extras)
        else:
            run["mail"] = "생략"
        run["ok"] = True
    except Exception as e:
        run["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        raise
    finally:
        run["finished"] = datetime.now(KST).strftime("%H:%M:%S")
        try:
            if mode == "live":
                write_run_log(run)
            elif mode == "rehearsal":
                write_diag(run, out_dir / "preview_diag.txt")
        except Exception as e:
            print(f"[main] 실행 기록 저장 실패(무시): {e}")


if __name__ == "__main__":
    main()
