@echo off
setlocal EnableExtensions
chcp 65001 >nul

echo Nix — instalação do binário
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
    echo.
    echo A instalacao nao concluiu. Veja a mensagem acima e tente de novo.
)

call :maybe_pause
endlocal & exit /b %EXITCODE%

:maybe_pause
echo %CMDCMDLINE% | find /I "/c" >nul
if not errorlevel 1 pause
exit /b 0
