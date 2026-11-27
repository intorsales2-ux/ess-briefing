"""수집 모듈 — 뉴스 RSS(국내 · 해외 · 데이터센터) · 전력거래소 공지 · 주가 시세.

2026-11 개편: 검색 창구를 넓혔다.
  - Google 뉴스 한국판(국내) + 영어판(해외) 두 창구를 쓴다.
  - 해외 전문매체는 RSS를 직접 구독한다(막히는 매체는 건너뛰고 계속 진행).
  - 데이터센터 검색어를 따로 둔다.
  - 기사마다 묶음(bucket: kr / global / datacenter)을 붙여, 편집 AI에게 묶음별 정원만큼 넘긴다.
    (예전에는 '최신 40건'만 넘겨 국내 기사가 많은 날 해외 기사가 잘렸다.)
"""
from __future__ import annotations
import calendar
import hashlib
import html
import re
import socket
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urljoin, urlparse

import feedparser
import requests

KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (compatible; IntoalBriefingBot/1.0)"}
BROWSER_UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8",
}
EDITIONS = {"ko": "hl=ko&gl=KR&ceid=KR:ko", "en": "hl=en-US&gl=US&ceid=US:en"}
BUCKETS = ("kr", "global", "datacenter")
DEFAULT_QUOTA = {"kr": 26, "global": 18, "datacenter": 12}
ID_PREFIX = {"kr": "K", "global": "G", "datacenter": "D", "notice": "N"}

DIAG: list[dict] = []  # 최근 수집의 창구별 결과(건수·오류) — 리허설 진단과 실행 기록에 쓴다


# ── 뉴스 RSS ──────────────────────────────────────────────
def google_news_url(query: str, edition: str = "ko") -> str:
    return f"https://news.google.com/rss/search?q={quote(query)}&{EDITIONS.get(edition, EDITIONS['ko'])}"


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text).replace("\xa0", " ")  # &amp; &#39; &nbsp; 등을 실제 글자로
    return re.sub(r"\s+", " ", text).strip()


def _core_title(title: str) -> str:
    """Google 뉴스가 제목 끝에 붙이는 ' - 매체명' 꼬리를 뗀다(매체명 안의 붙임표는 건드리지 않는다)."""
    return re.sub(r"\s+[-–|]\s+(?!.*\s[-–|]\s).{2,40}$", "", title)


def _title_key(title: str) -> str:
    """제목 중복 판정용 열쇠 — 매체명 꼬리를 떼고, 글자·숫자만 남겨 비교한다."""
    return hashlib.md5(re.sub(r"\W", "", _core_title(title).lower()).encode()).hexdigest()


def _published(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        st = getattr(entry, attr, None)
        if st:  # feedparser의 시각은 UTC — timegm으로 그대로 읽는다(mktime은 서버 시간대만큼 어긋남)
            return datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc).astimezone(KST)
    return None


def feed_plan(news_cfg: dict) -> list[dict]:
    """설정 → 수집 창구 목록. 직접 구독(요약문이 충실)을 먼저, Google 뉴스 검색을 뒤에 둔다."""
    plan: list[dict] = []
    feeds = news_cfg.get("feeds") or {}
    for bucket in BUCKETS:
        for url in feeds.get(bucket, []) or []:
            plan.append({"bucket": bucket, "kind": "rss", "label": urlparse(url).netloc.replace("www.", ""), "url": url})
    for url in news_cfg.get("extra_rss", []) or []:  # 예전 설정 호환
        plan.append({"bucket": "kr", "kind": "rss", "label": urlparse(url).netloc.replace("www.", ""), "url": url})
    q = news_cfg.get("queries") or {}
    groups = [("kr", "ko", q.get("kr")), ("global", "en", q.get("global")),
              ("datacenter", "ko", q.get("datacenter_ko")), ("datacenter", "en", q.get("datacenter_en"))]
    if not q and news_cfg.get("google_news_queries"):  # 예전 설정 파일 그대로여도 돌아가게
        groups = [("kr", "ko", news_cfg["google_news_queries"])]
    for bucket, edition, queries in groups:
        for query in queries or []:
            plan.append({"bucket": bucket, "kind": f"gnews-{edition}", "label": query,
                         "url": google_news_url(query, edition)})
    return plan


def _fetch(item: dict):
    if item["kind"] == "rss":  # 전문매체 직접 구독 — 브라우저처럼 요청하고 15초 넘으면 포기
        res = requests.get(item["url"], headers=BROWSER_UA, timeout=15)
        res.raise_for_status()
        return feedparser.parse(res.content)
    return feedparser.parse(item["url"])


def collect_news(cfg: dict) -> list[dict]:
    """모든 창구에서 최근 기사를 모아 제목 중복을 없앤다. 각 기사에 bucket(묶음)이 붙는다."""
    news_cfg = cfg.get("news", {})
    now = datetime.now(KST)
    lookback = timedelta(hours=news_cfg.get("lookback_hours", 720))
    hard_limit = timedelta(days=news_cfg.get("max_age_days_hard_limit", 45))
    cutoff = max(now - lookback, now - hard_limit)  # 두 기준 중 더 엄격한 쪽

    DIAG.clear()
    items, seen = [], set()
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(20)  # 응답 없는 창구 하나가 전체 발행을 붙잡지 못하게
    try:
        _collect_into(items, seen, feed_plan(news_cfg), cutoff)
    finally:
        socket.setdefaulttimeout(old_timeout)
    items.sort(key=lambda x: x["published"], reverse=True)
    out, n = [], {b: 0 for b in BUCKETS}
    for a in items:  # 묶음별 150건까지만 들고 간다
        if n[a["bucket"]] < 150:
            n[a["bucket"]] += 1
            out.append(a)
    return out


def _snippet(entry, title: str, source: str, rich: bool) -> str:
    """요약문 — Google 뉴스 검색 결과는 '제목 + 매체명'을 되풀이할 뿐이라 새 내용이 없으면 비운다."""
    text = _clean(getattr(entry, "summary", ""))
    rest = text.replace(title, "").replace(_core_title(title), "").replace(source, "").strip(" -–|·")
    if len(rest) < 20:
        return ""
    return text[:500 if rich else 300]


def _collect_into(items: list, seen: set, plan: list[dict], cutoff: datetime) -> None:
    for item in plan:
        row = {"bucket": item["bucket"], "kind": item["kind"], "label": item["label"], "got": 0, "kept": 0, "err": ""}
        DIAG.append(row)
        try:
            feed = _fetch(item)
        except Exception as exc:
            row["err"] = f"{type(exc).__name__}: {str(exc)[:90]}"
            continue
        entries = list(getattr(feed, "entries", []) or [])
        row["got"] = len(entries)
        if not entries and getattr(feed, "bozo", 0):
            row["err"] = f"형식 오류: {str(getattr(feed, 'bozo_exception', ''))[:80]}"
        feed_title = _clean((getattr(feed, "feed", {}) or {}).get("title", ""))[:30]
        for e in entries[:25]:
            title = _clean(getattr(e, "title", ""))
            if not title:
                continue
            key = _title_key(title)
            if key in seen:
                continue
            published = _published(e)
            # 날짜 필터(엄격): 기준보다 오래됐거나 날짜를 못 읽은 기사는 제외 — 묵은 기사 유입 방지
            if published is None or published < cutoff:
                continue
            seen.add(key)
            source = ""
            if getattr(e, "source", None):
                source = getattr(e.source, "title", "") or ""
            source = source or (item["label"] if item["kind"] == "rss" else feed_title)
            items.append({
                "bucket": item["bucket"],
                "title": title,
                "url": getattr(e, "link", ""),
                "source": source,
                "published": published.strftime("%Y-%m-%d %H:%M"),
                "snippet": _snippet(e, title, source, item["kind"] == "rss"),
            })
            row["kept"] += 1


def select_candidates(articles: list[dict], cfg: dict) -> tuple[dict, dict]:
    """기출 제외를 마친 기사 → 편집 AI에게 넘길 묶음별 후보와 '번호 → 기사' 대응표.

    기사 주소(Google 뉴스 주소는 200자가 넘는다)를 AI와 주고받지 않고 짧은 번호(K01·G03·D02)로
    대신한다. 주소 오타가 원천 차단되고 토큰도 크게 줄어든다.
    """
    quota = dict(DEFAULT_QUOTA)
    quota.update((cfg.get("news", {}).get("candidates") or {}))
    picked: dict[str, list] = {b: [] for b in BUCKETS}
    notices = []
    for a in articles:  # 이미 최신순
        b = a.get("bucket", "kr")
        if b == "notice":
            notices.append(a)
        elif b in picked and len(picked[b]) < int(quota.get(b, 0)):
            picked[b].append(a)
    payload, table = {}, {}
    for b, rows in list(picked.items()) + [("notice", notices[:10])]:
        payload_key = "notices" if b == "notice" else b
        payload[payload_key] = []
        for i, a in enumerate(rows, 1):
            aid = f"{ID_PREFIX[b]}{i:02d}"
            table[aid] = a
            payload[payload_key].append({"id": aid, "title": a["title"], "source": a.get("source", ""),
                                         "published": a.get("published", ""), "snippet": a.get("snippet", "")})
    return payload, table


def diag_lines() -> list[str]:
    """수집 창구별 결과를 사람이 읽는 줄로."""
    name = {"kr": "국내", "global": "해외", "datacenter": "데이터센터"}
    out = []
    for r in DIAG:
        kind = {"rss": "직접구독", "gnews-ko": "구글뉴스(한국판)", "gnews-en": "구글뉴스(영어판)"}.get(r["kind"], r["kind"])
        tail = f" · 오류: {r['err']}" if r["err"] else ""
        out.append(f"[{name.get(r['bucket'], r['bucket'])}] {kind} '{r['label']}' — 받음 {r['got']} · 채택 {r['kept']}{tail}")
    return out


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
                    "bucket": "notice",
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
