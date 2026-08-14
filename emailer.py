"""이메일 발송 모듈 — 완성된 브리핑 HTML을 대표이사 등 수신자에게 송부."""
from __future__ import annotations

import re
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate


FILENAME = "INTOR-ess-briefing.html"


def _cover_html(html: str, site_url: str = "") -> str:
    """메일 본문 표지 — 모든 스타일 인라인(메일 앱이 벗겨낼 옷이 없음)."""
    m = re.search(r"제(20\d\d-\d+)호", html)
    issue = "제" + m.group(1) + "호" if m else "오늘 호"
    d = re.search(r"발행 (20\d\d\.\d\d\.\d\d\([^)]+\))", html)
    pub = d.group(1) if d else ""

    # 3줄 요약 추출(각 <li> 안 <b>…</b>)
    lines = []
    for mm in re.finditer(r'<li><span class="n">\d</span><div><b>(.{10,300}?)</b>', html, re.S):
        txt = re.sub(r"<[^>]+>", "", mm.group(1)).strip()
        if txt:
            lines.append(txt[:130])
        if len(lines) == 3:
            break

    # KPI 카드(라벨/값) 최대 2개
    kpis = []
    for mm in re.finditer(r'<div class="k-label">(.{2,60}?)</div>\s*<div class="k-value">(.{1,60}?)</div>', html, re.S):
        lab = re.sub(r"<[^>]+>", "", mm.group(1)).strip()
        val = re.sub(r"<[^>]+>", "", mm.group(2)).strip()
        if lab and val:
            kpis.append((lab, val))
        if len(kpis) == 2:
            break

    base = site_url.rstrip("/") if site_url else ""
    today_link = base + "/" if base else ""
    list_link = base + "/list.html" if base else ""

    li_html = ""
    for i, ln in enumerate(lines, 1):
        li_html += (
            '<tr><td style="padding:0 0 11px;vertical-align:top;width:26px;">'
            '<span style="display:inline-block;width:20px;height:20px;line-height:20px;text-align:center;'
            'background:#4dd0a4;color:#07130d;border-radius:10px;font-size:11px;font-weight:800;">' + str(i) + '</span></td>'
            '<td style="padding:0 0 11px;font-size:13px;color:#2c3742;line-height:1.65;">' + ln + '</td></tr>'
        )

    kpi_html = ""
    if kpis:
        cells = ""
        for lab, val in kpis:
            cells += (
                '<td style="width:50%;padding:12px 14px;background:#f4f7f9;border:1px solid #e3e8ee;border-radius:10px;">'
                '<div style="font-size:10.5px;color:#8a949e;letter-spacing:.04em;">' + lab + '</div>'
                '<div style="font-size:17px;font-weight:800;color:#0e1720;margin-top:3px;">' + val + '</div></td>'
                '<td style="width:10px;"></td>'
            )
        kpi_html = ('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                    'style="margin:4px 0 18px;"><tr>' + cells[:-len('<td style="width:10px;"></td>')] + '</tr></table>')

    btns = ""
    if base:
        btns = (
            '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:6px 0 4px;"><tr>'
            '<td style="background:#0e1720;border-radius:26px;">'
            '<a href="' + today_link + '" style="display:inline-block;padding:13px 30px;color:#ffffff;'
            'text-decoration:none;font-size:14px;font-weight:700;">오늘 지면 읽기</a></td>'
            '<td style="width:10px;"></td>'
            '<td style="border:1px solid #cfd7de;border-radius:26px;">'
            '<a href="' + list_link + '" style="display:inline-block;padding:13px 24px;color:#0e1720;'
            'text-decoration:none;font-size:14px;font-weight:700;">지난 호 목록</a></td>'
            '</tr></table>'
        )

    return """<div style="margin:0;padding:24px 12px;background:#eef2f5;font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#ffffff;border:1px solid #dfe5ea;border-radius:14px;overflow:hidden;">
  <tr><td style="background:#0e1720;padding:20px 26px;">
    <div style="font-size:21px;font-weight:900;color:#ffffff;letter-spacing:1px;">INTO<span style="color:#4dd0a4;">R</span></div>
    <div style="font-size:10.5px;color:#8b96a2;letter-spacing:.16em;margin-top:4px;">ESS MARKET INTELLIGENCE &middot; DAILY</div>
  </td></tr>
  <tr><td style="padding:24px 26px 4px;">
    <div style="font-size:19px;font-weight:800;color:#0e1720;">ESS 시황 데일리 브리핑</div>
    <div style="font-size:12.5px;color:#7d8791;margin-top:6px;padding-bottom:16px;border-bottom:1px solid #eceff2;">""" + issue + ((" &middot; " + pub) if pub else "") + """</div>
  </td></tr>
  <tr><td style="padding:18px 26px 0;">
    <div style="font-size:11px;font-weight:800;color:#4dd0a4;letter-spacing:.1em;margin-bottom:12px;">TODAY IN 3 LINES</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">""" + li_html + """</table>
  </td></tr>
  <tr><td style="padding:8px 26px 0;">""" + kpi_html + """</td></tr>
  <tr><td style="padding:4px 26px 26px;">""" + btns + """
    <div style="font-size:11.5px;color:#98a2ad;margin-top:14px;line-height:1.6;">
      전체 지면 &middot; 기사별 상세 보고서 출력 &middot; 독자 댓글은 위 링크에서 이용하실 수 있습니다.<br>
      &copy; 인투알 영업팀 &middot; 내부용 &middot; 매 영업일 07:30 자동 발행
    </div>
  </td></tr>
 </table>
</div>"""


def send_briefing(html: str, subject: str, plain_summary: str = "", site_url: str = "") -> bool:
    host = os.environ.get("SMTP_HOST")
    user = os.environ.get("SMTP_USER")
    pw = os.environ.get("SMTP_PASS")
    mail_from = os.environ.get("MAIL_FROM", user or "")
    mail_to = [a.strip() for a in os.environ.get("MAIL_TO", "").split(",") if a.strip()]
    port = int(os.environ.get("SMTP_PORT", "587"))

    if not (host and user and pw and mail_to):
        print("[emailer] SMTP 환경변수 미설정 → 발송 건너뜀 "
              "(SMTP_HOST/SMTP_USER/SMTP_PASS/MAIL_TO 필요)")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = ", ".join(mail_to)
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(plain_summary or
                    (f"인투알 ESS 데일리 브리핑이 도착했습니다. 웹에서 보기: {site_url}" if site_url else
                     f"인투알 ESS 데일리 브리핑이 도착했습니다. 첨부된 {FILENAME} 파일을 브라우저로 열어주세요."))
    msg.add_alternative(_cover_html(html, site_url), subtype="html")
    # 본문은 어떤 메일 앱에서도 깨지지 않는 '표지'만 — 전체 지면은 첨부 파일로 열람
    if not site_url:   # 웹 주소가 없을 때만 첨부(오프라인 보험)
        msg.add_attachment(html.encode("utf-8"), maintype="text", subtype="html",
                           filename=FILENAME)

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as s:
                s.login(user, pw)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(user, pw)
                s.send_message(msg)
        print(f"[emailer] 발송 완료 → {', '.join(mail_to)}")
        return True
    except Exception as exc:
        print(f"[emailer] 발송 실패: {exc}")
        return False
