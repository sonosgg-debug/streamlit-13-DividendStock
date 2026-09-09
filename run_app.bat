@echo off
echo ========================================================
echo   Dividend Stock TOP 100 Dashboard
echo ========================================================
echo.
cd /d "%~dp0"
python -m streamlit run app.py
pause
