@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo Nix — instalação do ambiente e configuração
echo.

set "BOOTSTRAP=%~dp0scripts\bootstrap.py"
if not exist "%BOOTSTRAP%" (
    echo [erro] Nao achei scripts\bootstrap.py.
    echo Rode setup.bat na raiz do repositorio Nix.
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
%PYCMD% "%BOOTSTRAP%" %*
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" goto :fail

echo.
echo Pronto. Depois rode: .venv\Scripts\python.exe -m nix doctor
echo Para indexar o vault: .venv\Scripts\python.exe -m nix sync
goto :end

:fail
if not defined EXITCODE set "EXITCODE=1"
echo.
echo A instalacao nao concluiu. Veja a mensagem acima e tente de novo.

:end
echo.
pause
exit /b %EXITCODE%
