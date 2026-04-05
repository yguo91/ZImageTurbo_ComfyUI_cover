@echo off
cd /d "%~dp0"
echo Starting ZImageTurbo...
echo Installing / verifying dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install dependencies.
    echo Make sure Python and pip are available and try again.
    pause
    exit /b 1
)

python run.py
pause
