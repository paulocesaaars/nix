@echo off
setlocal EnableExtensions
set "ROOT=%~dp0.."
if exist "%ROOT%\.venv\Scripts\python.exe" (
  "%ROOT%\.venv\Scripts\python.exe" -P -m nix %*
  exit /b %ERRORLEVEL%
)
if exist "%ROOT%\.venv\bin\python" (
  "%ROOT%\.venv\bin\python" -P -m nix %*
  exit /b %ERRORLEVEL%
)
if defined NIX_HOME if exist "%NIX_HOME%\.venv\Scripts\python.exe" (
  "%NIX_HOME%\.venv\Scripts\python.exe" -P -m nix %*
  exit /b %ERRORLEVEL%
)
if defined NIX_HOME if exist "%NIX_HOME%\.venv\bin\python" (
  "%NIX_HOME%\.venv\bin\python" -P -m nix %*
  exit /b %ERRORLEVEL%
)
echo [erro] Nao achei o interpretador em %ROOT%\.venv. PATH permanente: veja o INSTALL.md. So nesta sessao: call "%ROOT%\bin\env.cmd"
exit /b 1
