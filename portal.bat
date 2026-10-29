@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"

set "portalPython=%~dp0.venv\Scripts\python.exe"
if "%~1"=="" goto menu

set "portalCommand=%~1"
if /I "%portalCommand%"=="deploy" goto deploy
if /I "%portalCommand%"=="start" goto run
if /I "%portalCommand%"=="status" goto run
if /I "%portalCommand%"=="stop" goto run
if /I "%portalCommand%"=="foreground" goto run
goto usage

:deploy
where python.exe >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python 3.10 or later was not found in PATH.
    exit /b 1
)
if not exist "%portalPython%" (
    python.exe -X utf8 -c "print('\u6b63\u5728\u521b\u5efa Python \u865a\u62df\u73af\u5883\u2026\u2026')"
    python.exe -m venv "%~dp0.venv"
    if errorlevel 1 exit /b 1
)
set "skipDependencies=0"
for %%A in (%*) do if /I "%%~A"=="-SkipDependencyInstall" set "skipDependencies=1"
for %%A in (%*) do if /I "%%~A"=="--skip-dependency-install" set "skipDependencies=1"
if "%skipDependencies%"=="0" (
    "%portalPython%" -X utf8 -c "print('\u6b63\u5728\u5b89\u88c5\u6216\u66f4\u65b0\u9879\u76ee\u4f9d\u8d56\u2026\u2026')"
    "%portalPython%" -m pip install -r "%~dp0requirements-business.txt"
    if errorlevel 1 exit /b 1
)
goto run

:run
if not exist "%portalPython%" (
    where python.exe >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python environment is missing. Run portal.bat deploy.
    ) else (
        python.exe -X utf8 -c "print('\u9519\u8bef\uff1a\u9879\u76ee\u865a\u62df\u73af\u5883\u4e0d\u5b58\u5728\uff0c\u8bf7\u5148\u8fd0\u884c\uff1aportal.bat deploy')"
    )
    exit /b 1
)
"%portalPython%" -X utf8 -m portal.windows_control %*
exit /b %ERRORLEVEL%

:menu
if exist "%portalPython%" (
    "%portalPython%" -X utf8 -m portal.windows_control menu
    exit /b %ERRORLEVEL%
)
where python.exe >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python 3.10 or later was not found in PATH.
    exit /b 1
)
python.exe -X utf8 -m portal.windows_control menu
exit /b %ERRORLEVEL%

:usage
if exist "%portalPython%" (
    "%portalPython%" -X utf8 -m portal.windows_control usage
    exit /b 2
)
echo Usage: portal.bat deploy, start, status, stop, or foreground
exit /b 2
