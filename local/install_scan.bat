@echo off
echo Installing the browser used by the account scan (once)...
python -m pip install --upgrade pip
python -m pip install playwright
python -m playwright install chromium
echo.
echo Done. Now copy credentials.env.example to credentials.env and fill in the accounts.
pause
