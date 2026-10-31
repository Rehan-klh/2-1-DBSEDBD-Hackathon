@echo off
cd /d "%~dp0"

echo Installing/checking required packages...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install requirements. Make sure Python and pip are installed.
    pause
    exit /b 1
)

start "" /b cmd /c "timeout /t 2 /nobreak >nul & start "" http://127.0.0.1:5000"
python app.py

if errorlevel 1 (
    echo Shiftwise stopped with an error.
    pause
)
