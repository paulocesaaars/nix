@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo Nix — desinstalacao
echo.

set "UNINSTALL=%~dp0scripts\uninstall.py"
if not exist "%UNINSTALL%" (
    echo [erro] Nao achei scripts\uninstall.py.
    echo Rode uninstall.bat na raiz do repositorio Nix.
    goto :fail
)

set "PYCMD="

where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYCMD=py -3"
)

if not defined PYCMD (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
        if not errorlevel 1 set "PYCMD=python"
    )
)

if not defined PYCMD (
    where python3 >nul 2>&1
    if not errorlevel 1 (
        python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
        if not errorlevel 1 set "PYCMD=python3"
    )
)

if not defined PYCMD (
    echo [erro] Python 3.11+ nao encontrado.
    echo Instale em https://www.python.org/downloads/ e marque "Add python.exe to PATH".
    goto :fail
)

echo Usando: %PYCMD%
%PYCMD% "%UNINSTALL%" %*
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" goto :fail

call :maybe_pause
endlocal & exit /b 0

:fail
if not defined EXITCODE set "EXITCODE=1"
echo.
echo A desinstalacao nao concluiu. Veja a mensagem acima e tente de novo.
call :maybe_pause
endlocal & exit /b %EXITCODE%

:maybe_pause
echo %CMDCMDLINE% | find /I "/c" >nul
if not errorlevel 1 pause
exit /b 0
