"""수집 모듈 — 뉴스 RSS · 전력거래소 공지 · 주가 시세."""
from __future__ import annotations
import hashlib
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urljoin

import feedparser
import requests

KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (compatible; IntoalBriefingBot/1.0)"}


# ── 뉴스 RSS ──────────────────────────────────────────────
def google_news_url(query: str) -> str:
    return f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko"


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def collect_news(cfg: dict) -> list[dict]:
    """Google News RSS(+추가 RSS)에서 최근 기사를 수집·중복 제거."""
    news_cfg = cfg.get("news", {})
    now = datetime.now(KST)
    lookback = timedelta(hours=news_cfg.get("lookback_hours", 720))
    hard_limit = timedelta(days=news_cfg.get("max_age_days_hard_limit", 45))
    # 두 기준 중 더 엄격한(=더 최근인) 쪽을 실제 컷오프로 사용
    cutoff = max(now - lookback, now - hard_limit)

    feed_urls = [google_news_url(q) for q in news_cfg.get("google_news_queries", [])]
    feed_urls += news_cfg.get("extra_rss", []) or []

    items, seen = [], set()
    for url in feed_urls:
        try:
            feed = feedparser.parse(url)
        except Exception:
            continue
        for e in feed.entries[:20]:
            title = _clean(getattr(e, "title", ""))
            if not title:
                continue
            key = hashlib.md5(re.sub(r"\W", "", title.lower()).encode()).hexdigest()
            if key in seen:
                continue
            published = None
            for attr in ("published_parsed", "updated_parsed"):
                st = getattr(e, attr, None)
                if st:
                    published = datetime.fromtimestamp(time.mktime(st), tz=timezone.utc).astimezone(KST)
                    break
            # 날짜 필터(엄격): 기준일보다 오래됐거나, 날짜를 아예 못 읽은
            # 기사는 오래된 기사가 새어 들어오는 것을 막기 위해 제외한다.
            if published is None or published < cutoff:
                continue
            seen.add(key)
            source = ""
            if getattr(e, "source", None):
                source = getattr(e.source, "title", "") or ""
            items.append({
                "title": title,
                "url": getattr(e, "link", ""),
                "source": source or _clean(feed.feed.get("title", ""))[:30],
                "published": published.strftime("%Y-%m-%d %H:%M") if published else "",
                "snippet": _clean(getattr(e, "summary", ""))[:400],
            })
    items.sort(key=lambda x: x["published"], reverse=True)
    return items[:120]


# ── 전력거래소(KPX) 공지 — ESS 입찰 공고 감지 ─────────────
def collect_kpx_notices(cfg: dict) -> list[dict]:
    kpx = cfg.get("kpx", {})
    if not kpx.get("enabled", True):
        return []
    board_url = kpx.get("board_url", "")
    keywords = kpx.get("keywords", ["ESS", "입찰"])
    try:
        from bs4 import BeautifulSoup
        res = requests.get(board_url, headers=UA, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        out = []
        for a in soup.select("a"):
            text = _clean(a.get_text())
            href = a.get("href") or ""
            if len(text) < 8 or not href:
                continue
            if any(k in text for k in keywords):
                out.append({
                    "title": f"[전력거래소 공지] {text}",
                    "url": urljoin(board_url, href),
                    "source": "전력거래소",
                    "published": "",
                    "snippet": "전력거래소 공지사항 게시글 (입찰·공고 관련 키워드 매칭)",
                })
            if len(out) >= 10:
                break
        return out
    except Exception as exc:  # 사이트 구조 변경 등 — 파이프라인은 계속 진행
        print(f"[collectors] KPX 공지 수집 실패(무시하고 진행): {exc}")
        return []


# ── 주가 시세 (yfinance, 지연 시세) ──────────────────────
def _fmt_price(value: float, symbol: str) -> str:
    if symbol.endswith(".KS") or symbol.endswith(".KQ"):
        return f"{value:,.0f}원"
    if symbol.endswith(".SZ") or symbol.endswith(".SS"):
        return f"¥{value:,.2f}"
    return f"${value:,.2f}"


def collect_stocks(cfg: dict) -> dict | None:
    st = cfg.get("stocks", {})
    if not st.get("enabled", True):
        return None
    try:
        import yfinance as yf
    except ImportError:
        print("[collectors] yfinance 미설치 → 주가는 샘플로 대체")
        return None

    def rows(entries):
        out = []
        for ent in entries:
            sym = ent["yf"]
            try:
                hist = yf.Ticker(sym).history(period="5d")["Close"].dropna()
                last, prev = float(hist.iloc[-1]), float(hist.iloc[-2])
                pct = (last - prev) / prev * 100
                direction = "up" if pct > 0.05 else "down" if pct < -0.05 else "flat"
                arrow = {"up": "▲", "down": "▼", "flat": "—"}[direction]
                out.append({
                    "name": ent["name"], "ticker": ent["label"], "yf": sym,
                    "price": _fmt_price(last, sym),
                    "change": f"{arrow} {pct:+.1f}%",
                    "dir": direction, "events": "—",
                })
            except Exception as exc:
                print(f"[collectors] 시세 실패 {sym}: {exc}")
                out.append({"name": ent["name"], "ticker": ent["label"], "yf": sym,
                            "price": "—", "change": "—", "dir": "flat", "events": "—"})
        return out

    try:
        return {
            "sample": False,
            "asof": datetime.now(KST).strftime("%m.%d %H:%M"),
            "kr": rows(st.get("kr", [])),
            "global_": rows(st.get("global", [])),
        }
    except Exception as exc:
        print(f"[collectors] 주가 수집 전체 실패: {exc}")
        return None
