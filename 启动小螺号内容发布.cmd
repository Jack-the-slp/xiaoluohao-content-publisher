@echo off
cd /d "%~dp0"
if not exist ".venv\.setup-complete" (
  echo First run: installing local dependencies. Please wait...
  if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv || goto :fail
  ".venv\Scripts\python.exe" -m pip install -e . || goto :fail
  ".venv\Scripts\python.exe" -m patchright install chromium || goto :fail
  ".venv\Scripts\python.exe" -m playwright install chromium || goto :fail
  type nul > ".venv\.setup-complete"
)
if not exist "conf.py" copy /y "conf.example.py" "conf.py" >nul
if not exist ".wechatsync\node_modules\.bin\wechatsync.cmd" (
  where npm.cmd >nul 2>&1
  if not errorlevel 1 npm.cmd install --prefix .wechatsync @wechatsync/cli
)
".venv\Scripts\python.exe" xiaoluohao_publisher.py
exit /b %errorlevel%
:fail
echo Setup failed. Please send the error above for diagnosis.
pause
exit /b 1
