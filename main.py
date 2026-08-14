"""인투알 ESS 데일리 브리핑 — 파이프라인 오케스트레이터.

사용법:
  python main.py --dry-run          # API 키 없이 샘플 데이터로 렌더링(미리보기)
  python main.py                    # 수집 → AI 요약 → 렌더링 → 이메일 발송
  python main.py --no-email         # 이메일 발송 생략
"""
from __future__ import annotations
import argparse
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

import render

BASE = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def load_config() -> dict:
    return yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))


def _issue_fields(now: datetime) -> dict:
    nxt = now + timedelta(days=1)
    while nxt.weekday() >= 5:  # 주말 건너뛰기
        nxt += timedelta(days=1)
    return {
        "issue_no": f"제{now.year}-{now.timetuple().tm_yday:03d}호",
        "date_str": now.strftime(f"%Y.%m.%d({WEEKDAY_KO[now.weekday()]}) %H:%M KST"),
        "date_short": now.strftime("%Y.%m.%d"),
        "next_issue": nxt.strftime(f"%m.%d({WEEKDAY_KO[nxt.weekday()]}) 07:30"),
    }


def build_dry_run_data(now: datetime, cfg=None) -> dict:
    """샘플 데이터에 오늘 날짜만 갱신 — API 키 없이 디자인/발송 흐름 점검용."""
    data = json.loads((BASE / "data" / "sample_data.json").read_text(encoding="utf-8"))
    data["_dry"] = True  # 샘플 호수·날짜 고정(실데이터 명시) + 롤링 상태 저장 안 함
    if cfg and cfg.get("comments_api_url"):
        data["comments_api_url"] = cfg["comments_api_url"]
    return data


def build_live_data(cfg: dict, now: datetime) -> dict:
    import ai
    import collectors
    import dedup

    if now.weekday() == 0:
        cfg["news"]["lookback_hours"] = max(cfg["news"]["lookback_hours"], 96)
        print("[main] 월요일 → 수집창 96시간(금~일 포함)으로 확장")

    print("[main] 1/4 뉴스·공고 수집 중...")
    articles = collectors.collect_news(cfg) + collectors.collect_kpx_notices(cfg)
    n_all = len(articles)
    seen = dedup.load_seen()
    articles, n_dup = dedup.filter_new(articles, seen)
    print(f"[main]   수집 {n_all}건 → 기출 {n_dup}건 제외 → 후보 {len(articles)}건")

    print("[main] 2/4 Claude 편집 중 (v10 지면 패키지)...")
    import render as _r
    state = _r._load_state()
    issue = _issue_fields(now)
    pkg = ai.daily_package(articles, {"next_spot": state["next_spot"], "next_know": state["next_know"]}, issue)

    data = dict(pkg)
    data.update(issue)
    data.setdefault("mast", {})
    data["mast"].setdefault("range", f"직전 발행 이후 ~ {now:%m.%d %H:%M}")
    data.setdefault("calendar", None)
    data["_dry"] = False
    data["comments_api_url"] = cfg.get("comments_api_url", "") or data.get("comments_api_url", "")
    data["site_url"] = cfg.get("site_url", "")
    return data


def main() -> None:
    ap = argparse.ArgumentParser(description="인투알 ESS 데일리 브리핑 파이프라인")
    ap.add_argument("--dry-run", action="store_true", help="샘플 데이터로 렌더링만 수행")
    ap.add_argument("--no-email", action="store_true", help="이메일 발송 생략")
    args = ap.parse_args()

    try:  # .env 지원(선택)
        from dotenv import load_dotenv
        load_dotenv(BASE / ".env")
    except ImportError:
        pass

    import os
    cfg = load_config()
    now = datetime.now(KST)

    if args.dry_run or not os.environ.get("ANTHROPIC_API_KEY"):
        if not args.dry_run:
            print("[main] ANTHROPIC_API_KEY 없음 → dry-run 모드로 전환")
        data = build_dry_run_data(now, cfg)
        mode = "dry-run"
    else:
        data = build_live_data(cfg, now)
        mode = "live"

    print("[main] 4/4 렌더링 중...")
    out_dir = BASE / cfg.get("output", {}).get("dir", "output")
    out_path = render.render_to_file(data, out_dir / "index.html")
    if cfg.get("output", {}).get("archive", True):
        arch = out_dir / "archive" / f"{now:%Y-%m-%d}.html"
        arch.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(out_path, arch)
    print(f"[main] 완료({mode}) → {out_path}")

    # 시세 자동 기입 — 실패해도 발행은 계속(보드는 '—' 유지)
    try:
        import stock_board
        print("[main] 주가 보드 기입 중 (야후 확정 종가)...")
        stock_board.fill(str(out_path))
        if cfg.get("output", {}).get("archive", True):
            shutil.copy(out_path, arch)  # 숫자 기입본으로 아카이브 갱신
    except Exception as e:
        print(f"[main] 시세 기입 건너뜀({type(e).__name__}: {e}) — 보드는 '—' 상태로 발행됩니다.")
        print("        인터넷 연결과 'pip install yfinance' 상태를 확인하세요.")

    if mode == "live":  # 발행 성공 → 기출 목록 갱신 (에디터 v2 · 다음 호 중복 방지)
        import dedup
        urls = [c.get("url") for s in data.get("news_sections", []) for c in s.get("cards", []) if c.get("url")]
        urls += [b.get("url") for b in data.get("briefs", []) if b.get("url")]
        dedup.record(urls, dedup.load_seen())
        print(f"[main] 기출 목록 갱신 → output/seen_urls.json (+{len(urls)}건)")

    if not args.no_email and mode == "live" and cfg.get("email", {}).get("enabled", True):
        import emailer
        subject = f"{cfg['email'].get('subject_prefix', '[인투알] ESS 데일리 브리핑')} {now:%m/%d}"
        summary = "\n".join(f"{i+1}. {l['head']} {l['body']}" for i, l in enumerate(data.get("three_lines", [])))
        emailer.send_briefing(out_path.read_text(encoding="utf-8", site_url=data.get("site_url", "")), subject, summary)


if __name__ == "__main__":
    main()
