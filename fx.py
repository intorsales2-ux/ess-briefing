"""환율 — 달러/원 · 위안/원.

1순위: 야후 파이낸스(주가 보드와 같은 창구) — 발행 시점 시세와 전일 종가 비교
2순위: Frankfurter(유럽중앙은행 고시 환율, 무료·열쇠 불필요) — 최근 고시와 직전 고시 비교
둘 다 실패하거나 값이 비정상이면 None — 지면에서는 환율 띠를 통째로 생략한다(지어낸 숫자 금지).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
FRANKFURTER = "https://api.frankfurter.dev/v1/{start}..?base=USD&symbols=KRW,CNY"


def _sane(usd: float, usd_prev: float, cny: float, cny_prev: float) -> bool:
    """자릿수 오류·데이터 글리치 방어 — 범위를 벗어나거나 하루 8% 넘게 움직였으면 버린다."""
    if not (700 < usd < 2500 and 700 < usd_prev < 2500 and 90 < cny < 400 and 90 < cny_prev < 400):
        return False
    return abs(usd / usd_prev - 1) < 0.08 and abs(cny / cny_prev - 1) < 0.08


def _item(label: str, now: float, prev: float) -> dict:
    diff = now - prev
    pct = (now / prev - 1) * 100
    direction = "up" if diff > 0.004 else "down" if diff < -0.004 else "flat"
    return {"label": label, "px": f"{now:,.2f}", "dir": direction,
            "chg": f"{abs(diff):,.2f}", "pct": "0.00%" if direction == "flat" else f"{pct:+.2f}%"}


def _yahoo() -> dict:
    import yfinance as yf
    data = yf.download(["KRW=X", "CNY=X", "CNYKRW=X"], period="10d", interval="1d",
                       auto_adjust=False, progress=False, group_by="ticker")

    def closes(sym):
        return data[sym]["Close"].dropna()

    usd = closes("KRW=X")
    u_now, u_prev = float(usd.iloc[-1]), float(usd.iloc[-2])
    try:  # 위안/원 직접 시세
        cny = closes("CNYKRW=X")
        c_now, c_prev = float(cny.iloc[-1]), float(cny.iloc[-2])
        if not _sane(u_now, u_prev, c_now, c_prev):
            raise ValueError("위안/원 직접 시세 비정상")
    except Exception:  # 없거나 이상하면 달러/원 ÷ 달러/위안으로 계산
        uc = closes("CNY=X")
        c_now, c_prev = u_now / float(uc.iloc[-1]), u_prev / float(uc.iloc[-2])
    if not _sane(u_now, u_prev, c_now, c_prev):
        raise ValueError(f"값 비정상(달러/원 {u_now:.2f}, 위안/원 {c_now:.2f})")
    stamp = datetime.now(KST).strftime("%m.%d %H:%M")
    return {"rows": [_item("달러/원", u_now, u_prev), _item("위안/원", c_now, c_prev)],
            "source": "Yahoo Finance", "note": f"{stamp} 조회 시세 · 전일 종가 대비"}


def _frankfurter() -> dict:
    import requests
    start = (datetime.now(KST) - timedelta(days=12)).strftime("%Y-%m-%d")
    res = requests.get(FRANKFURTER.format(start=start), timeout=12)
    res.raise_for_status()
    rates = res.json()["rates"]
    days = sorted(rates)[-2:]
    if len(days) < 2:
        raise ValueError("고시 환율이 이틀치 미만")
    (d0, d1) = days
    u_prev, u_now = float(rates[d0]["KRW"]), float(rates[d1]["KRW"])
    c_prev, c_now = u_prev / float(rates[d0]["CNY"]), u_now / float(rates[d1]["CNY"])
    if not _sane(u_now, u_prev, c_now, c_prev):
        raise ValueError(f"값 비정상(달러/원 {u_now:.2f}, 위안/원 {c_now:.2f})")
    return {"rows": [_item("달러/원", u_now, u_prev), _item("위안/원", c_now, c_prev)],
            "source": "유럽중앙은행 고시(Frankfurter)", "note": f"{d1[5:].replace('-', '.')} 고시 · 직전 고시 대비"}


def fetch() -> dict | None:
    """환율 두 줄을 돌려준다. 실패하면 None(환율 띠 생략)."""
    for name, fn in (("야후 파이낸스", _yahoo), ("Frankfurter", _frankfurter)):
        try:
            out = fn()
            print(f"[fx] {name} — 달러/원 {out['rows'][0]['px']} · 위안/원 {out['rows'][1]['px']}")
            return out
        except Exception as exc:
            print(f"[fx] {name} 실패({type(exc).__name__}: {str(exc)[:100]})")
    print("[fx] 환율을 받지 못했습니다 — 오늘 지면은 환율 띠 없이 발행합니다.")
    return None


if __name__ == "__main__":
    print(fetch())
