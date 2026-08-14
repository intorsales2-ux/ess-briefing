# -*- coding: utf-8 -*-
"""
인투알 ESS 브리핑 — 주가 보드 자동 기입 스크립트
사용법:
  1) 준비(최초 1회):  pip install yfinance
  2) 실행:           python stock_board.py intoal-ess-daily-2026-07-16.html
     → 야후 파이낸스에서 8종목 확정 종가를 받아 전일/전월/전년 대비를 계산,
       브리핑 HTML의 보드 칸(—)을 ▲▼ 등락으로 채워 저장합니다. (원본은 .bak 백업)
원칙: 확정 종가만 사용 — 계산 실패 종목은 '—'로 남기고 이유를 출력합니다.
"""
import sys, re, shutil
from datetime import timedelta

def _yf():
    try:
        import yfinance as yf
        return yf
    except ImportError:
        raise RuntimeError("yfinance 미설치 — pip install yfinance 후 다시 실행하세요")

# 야후 티커 → (보드 마커 ID, 통화 포맷)
TICKERS = {
    "373220.KS": ("373220", "krw"), "006400.KS": ("006400", "krw"),
    "096770.KS": ("096770", "krw"), "298040.KS": ("298040", "krw"),
    "TSLA":      ("TSLA",   "usd"), "FLNC":      ("FLNC",   "usd"),
    "3750.HK":   ("3750",   "hkd"), "300274.SZ": ("300274", "cny"),
}
UP, DN = "#f87171", "#60a5fa"   # 상승 빨강 · 하락 파랑 (국내 관례)

def fmt_price(v, cur):
    if cur == "krw": return f"{v:,.0f}원"
    sym = {"usd": "$", "hkd": "HK$", "cny": "¥"}[cur]
    return f"{sym}{v:,.2f}"

def fmt_pct(now, base):
    if base is None or base == 0: return "—"
    p = (now / base - 1) * 100
    if abs(p) < 0.005: return '<span style="color:#9aa4b2">0.00%</span>'
    arrow, color = ("▲", UP) if p > 0 else ("▼", DN)
    return f'<span style="color:{color}; font-weight:700">{arrow} {abs(p):.2f}%</span>'

def close_asof(closes, target_date):
    s = closes[closes.index <= target_date]
    return (float(s.iloc[-1]), s.index[-1].date()) if len(s) else (None, None)

def fill(path: str) -> bool:
    """브리핑 HTML의 시세 마커를 확정 종가·등락으로 기입. 성공 여부 반환."""
    html = open(path, encoding="utf-8").read()
    shutil.copy(path, str(path) + ".bak")

    yf = _yf()
    print("시세 수신 중 (야후 파이낸스, 1년 일봉)...")
    data = yf.download(list(TICKERS), period="400d", interval="1d",
                       auto_adjust=False, progress=False, group_by="ticker")
    stamp = None
    for yt, (sid, cur) in TICKERS.items():
        try:
            closes = data[yt]["Close"].dropna()
            last = float(closes.iloc[-1]); last_d = closes.index[-1]
            prev = float(closes.iloc[-2])
            m1, _ = close_asof(closes, last_d - timedelta(days=30))
            y1, _ = close_asof(closes, last_d - timedelta(days=365))
            vals = {"PX": fmt_price(last, cur), "D1": fmt_pct(last, prev),
                    "M1": fmt_pct(last, m1),   "Y1": fmt_pct(last, y1)}
            for f, v in vals.items():
                html = re.sub(f"<!--S{sid}:{f}-->.*?<!--/S{sid}:{f}-->",
                              f"<!--S{sid}:{f}-->{v}<!--/S{sid}:{f}-->", html, flags=re.S)
            stamp = stamp or last_d.date()
            print(f"  {yt:<10} {vals['PX']:>14}  전일 {closes.index[-2].date()}·전월·전년 계산 완료")
        except Exception as e:
            print(f"  {yt:<10} 실패 → '—' 유지 ({type(e).__name__}: {e})")
    if stamp:
        html = re.sub(r"<!--STAMP-->.*?<!--/STAMP-->",
                      f"<!--STAMP-->기준 {stamp} 종가<!--/STAMP-->", html, flags=re.S)
    open(path, "w", encoding="utf-8").write(html)
    print(f"[시세] 완료 — {path} 갱신 (백업 {path}.bak)")
    return stamp is not None


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: python stock_board.py <브리핑 HTML 파일명>")
    fill(sys.argv[1])


if __name__ == "__main__":
    main()
