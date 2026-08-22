@for %%I in ("%~dp0..") do @set "NIX_HOME=%%~fI"
@set "NIX_BIN=%NIX_HOME%\bin"
@set "_NIX_PATH_HIT="
@for %%P in ("%PATH:;=" "%") do @(
  @if /I "%%~P"=="%NIX_BIN%" @set "_NIX_PATH_HIT=1"
  @if /I "%%~P"=="%NIX_BIN%\" @set "_NIX_PATH_HIT=1"
)
@if not defined _NIX_PATH_HIT @set "PATH=%NIX_BIN%;%PATH%"
@set "NIX_BIN="
@set "_NIX_PATH_HIT="
