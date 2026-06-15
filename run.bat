@echo off
cd /d "%~dp0"
echo =====================================================
echo   WebScraper Dashboard
echo   Opening http://localhost:8765 ...
echo   Close this window to stop the server
echo =====================================================
echo.
start "" http://localhost:8765
C:\Users\15496\AppData\Local\Python\pythoncore-3.14-64\python.exe dashboard.py
pause
