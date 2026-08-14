@echo off
cd /d "%~dp0"
echo [INTOR] register daily schedule (Mon-Fri 07:30)
schtasks /Create /F /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 07:30 /TN "INTOR Briefing" /TR "\"%~dp0run_daily_with_email.bat\""
if %ERRORLEVEL%==0 (
  echo [INTOR] OK - task "INTOR Briefing" registered. See you tomorrow 07:30!
) else (
  echo [INTOR] FAILED - copy the message above and paste it to Claude.
)
pause
