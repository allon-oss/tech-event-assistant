@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Tech Event Assistant - Local Mode

pushd "%~dp0"
if errorlevel 1 goto directory_error

set "APP_MODE=local"
set "APP_PYTHON=%CD%\.venv\Scripts\python.exe"
set "APP_PORT=8501"

if not exist "%APP_PYTHON%" goto missing_venv
if not exist "app.py" goto missing_app
if not exist "launch_app.py" goto missing_app

"%APP_PYTHON%" -c "import streamlit" >nul 2>&1
if errorlevel 1 goto missing_dependencies

:find_port
"%APP_PYTHON%" -c "import socket,sys; s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1); s.bind(('127.0.0.1',int(sys.argv[1]))); s.close()" "%APP_PORT%" >nul 2>&1
if not errorlevel 1 goto launch
set /a APP_PORT+=1 >nul
if %APP_PORT% LEQ 8599 goto find_port
echo [ERROR] Ports 8501-8599 are unavailable. Close the conflicting program and retry.
goto failure

:launch
if not "%APP_PORT%"=="8501" echo Port 8501 is unavailable. Using port %APP_PORT% instead.
echo Starting the app in Local Mode...
echo Local URL: http://127.0.0.1:%APP_PORT%
echo Your browser will open after the server is ready.
echo The server runs in the background. Closing this window will not stop it.
echo.
"%APP_PYTHON%" "launch_app.py" --port "%APP_PORT%"
if errorlevel 1 goto launch_failed
popd
endlocal
exit /b 0

:missing_venv
echo [ERROR] Project Python was not found: .venv\Scripts\python.exe
echo Open PowerShell in the project folder and run the commands from README:
echo   py -3.12 -m venv .venv
echo   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
echo After installation, double-click start_app.bat again.
goto failure

:missing_app
echo [ERROR] app.py or launch_app.py was not found. Put this script in the project root folder.
goto failure

:missing_dependencies
echo [ERROR] Project Python could not run or Streamlit is not installed.
echo Check your virtual environment, then run this in the project PowerShell:
echo   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
goto failure

:launch_failed
echo.
echo [ERROR] The app failed to start or stopped with an error. See details above.
echo If the port became busy, double-click this script again to choose a free port.

:failure
echo.
pause
popd
endlocal
exit /b 1

:directory_error
echo [ERROR] Cannot access the folder containing this script.
pause
endlocal
exit /b 1
