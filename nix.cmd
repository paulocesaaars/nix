@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
if exist "%ROOT%.venv\Scripts\python.exe" (
  "%ROOT%.venv\Scripts\python.exe" -P -m nix %*
  exit /b %ERRORLEVEL%
)
if exist "%ROOT%.venv\bin\python" (
  "%ROOT%.venv\bin\python" -P -m nix %*
  exit /b %ERRORLEVEL%
)
echo [erro] Nao achei .venv. Rode setup.bat nesta pasta primeiro.
exit /b 1
