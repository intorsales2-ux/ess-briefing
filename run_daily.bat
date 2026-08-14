@echo off
cd /d "%~dp0"
echo [INTOAL] briefing robot - start
python main.py --no-email
echo.
echo [INTOAL] done. check the "output" folder.
pause