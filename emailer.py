"""이메일 발송 모듈 — 완성된 브리핑 HTML을 대표이사 등 수신자에게 송부."""
from __future__ import annotations
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate


FILENAME = "INTOR-ess-briefing.html"


def _cover_html(html: str, site_url: str = "") -> str:
    """메일 본문용 표지 — 모든 스타일 인라인(메일 앱이 벗겨낼 옷이 없음)."""
    import re as _re
    m = _re.search(r"제(20\d\d-\d+)호", html)
    issue = f"제{m.group(1)}호" if m else "오늘 호"
    d = _re.search(r"발행 (\d{4}\.\d{2}\.\d{2}\([^)]+\) \d{1,2}:\d{2})", html)
    pub = d.group(1) + " KST" if d else ""
    return f"""<div style="margin:0;padding:24px;background:#f4f6f8;font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #e3e8ee;border-radius:12px;">
  <tr><td style="background:#0e1720;border-radius:12px 12px 0 0;padding:18px 24px;">
    <span style="font-size:20px;font-weight:900;color:#ffffff;letter-spacing:1px;">INTO<span style="color:#4dd0a4;">R</span></span>
    <span style="color:#9aa4b2;font-size:11px;">&nbsp;· ESS MARKET INTELLIGENCE · DAILY</span>
  </td></tr>
  <tr><td style="padding:22px 24px 6px;">
    <div style="font-size:17px;font-weight:800;color:#111111;">ESS 시황 데일리 브리핑</div>
    <div style="font-size:13px;color:#556069;margin-top:5px;">{issue}{(" · " + pub) if pub else ""}</div>
  </td></tr>
  <tr><td style="padding:10px 24px 20px;font-size:13.5px;color:#333333;line-height:1.75;">
    오늘 지면이 도착했습니다.<br>
    <b>전체 지면은 첨부된 <span style="color:#0b7a55;">{FILENAME}</span> 파일을 눌러 브라우저로 열어주세요.</b><br>
    기사별 상세 보고서 출력(제목 옆 체크박스), 독자 댓글 등 모든 기능은 브라우저에서 작동합니다.<br>
    <span style="color:#8a949e;font-size:12px;">(메일 화면에서는 보안 정책상 지면 디자인과 기능이 표시되지 않습니다)</span>
    {("<div style='margin-top:18px;'><a href='" + site_url + "' style='display:inline-block;background:#0e1720;color:#ffffff;text-decoration:none;font-size:14px;font-weight:700;padding:12px 26px;border-radius:24px;'>🌐 웹에서 지면 보기 (댓글 작성 가능)</a></div>") if site_url else ""}
  </td></tr>
  <tr><td style="padding:0 24px 22px;font-size:11px;color:#98a2ad;">© 인투알 영업팀 · 내부용 · 이 메일은 발행 로봇이 자동 발송했습니다</td></tr>
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
                    f"인투알 ESS 데일리 브리핑이 도착했습니다. 첨부된 {FILENAME} 파일을 브라우저로 열어주세요.")
    msg.add_alternative(_cover_html(html, site_url), subtype="html")
    # 본문은 어떤 메일 앱에서도 깨지지 않는 '표지'만 — 전체 지면은 첨부 파일로 열람
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
