@echo off
REM SmartLab - one-time setup for Windows. Double-click, or run from the project folder.
setlocal
cd /d "%~dp0"

echo [1/4] Creating virtual environment...
if not exist venv (
    python -m venv venv
    if errorlevel 1 (
        echo Could not run Python. Install Python 3.10+ from python.org and tick "Add Python to PATH".
        pause & exit /b 1
    )
)

echo [2/4] Installing requirements...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 ( echo pip install failed. & pause & exit /b 1 )

echo [3/4] Creating .env file...
if not exist .env (
    copy .env.example .env >nul
    echo.
    echo *** .env was just created. Notepad will open: set DB_PASSWORD to your MySQL root password, save, and close it. ***
    notepad .env
) else (
    echo .env already exists - leaving it alone.
)

echo [4/4] Creating the database and demo data...
python setup_db.py

echo.
echo Setup finished. To start SmartLab, run run_windows.bat  (or press F5 in VS Code).
pause
