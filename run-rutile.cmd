@echo off
setlocal
pushd "%~dp0" || exit /b 1

if not exist ".venv\Scripts\python.exe" (
    echo Creating Rutile's Python 3.12 environment...
    py -3.12 -m venv .venv
    if errorlevel 1 goto setup_failed
)

".venv\Scripts\python.exe" -c "import rutile3, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo Installing Rutile's dependencies. This can take a few minutes...
    ".venv\Scripts\python.exe" -m pip install -c requirements-win-py312.txt -e .
    if errorlevel 1 goto setup_failed
)

".venv\Scripts\python.exe" scripts\run_app.py --open %*
if errorlevel 1 goto launch_failed
popd
exit /b 0

:setup_failed
echo Setup failed. Check that Python 3.12 and the Windows py launcher are installed.
goto failed

:launch_failed
echo Rutile could not start. Check the error above.

:failed
popd
pause
exit /b 1
