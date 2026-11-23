@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
 echo Python was not found. Install Python 3.10+ and retry.
 pause
 exit /b 1
)
if not exist "backend\.venv\Scripts\python.exe" (
 echo Creating backend virtual environment...
 python -m venv backend\.venv
)
call "backend\.venv\Scripts\activate.bat"
echo Installing / checking backend dependencies...
python -m pip install -r backend\requirements.txt
if errorlevel 1 (
 echo Dependency installation failed.
 pause
 exit /b 1
)
echo.
echo Starting WLA Test Lab at http://127.0.0.1:8000
start "WLA Test Lab Server" /D "%~dp0backend" cmd /k "python -m uvicorn app:APP --host 127.0.0.1 --port 8000"
timeout /t 3 /nobreak >nul
start http://127.0.0.1:8000
endlocal
