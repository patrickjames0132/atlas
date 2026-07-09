@echo off
rem Session bootstrap - run this first thing when a Claude Code session opens.
rem
rem Installs the pinned toolchain from .tool-versions via mise (python, uv,
rem nodejs, trivy), syncs the backend env, and installs + builds the frontend
rem so the working tree starts green. Cheap when everything is already current.
setlocal
cd /d "%~dp0.."

where mise >nul 2>nul
if %errorlevel%==0 (
  call mise install || exit /b 1
  call mise reshim || exit /b 1
) else (
  echo warning: mise not found -- skipping pinned-tool install (https://mise.jdx.dev)
)

call uv sync || exit /b 1
call npm install --prefix frontend || exit /b 1
call npm run build --prefix frontend || exit /b 1
