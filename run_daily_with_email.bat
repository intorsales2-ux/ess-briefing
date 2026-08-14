@echo off
cd /d "%~dp0"
echo [INTOR] briefing robot + email - start
python main.py
echo.
echo [INTOR] done. check the "output" folder and mailbox.
pause
