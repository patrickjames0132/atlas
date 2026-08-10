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

rem ATLAS_SKIP_TORCH=1 drops torch from the sync -- see setup.sh for the full
rem story. CI runs the .sh under bash on both runners, so this branch exists for
rem parity, not because CI uses it. Don't set it locally: `atlas serve` needs
rem torch to embed anything for real.
if "%ATLAS_SKIP_TORCH%"=="1" (
  call uv sync --all-groups --no-install-package torch || exit /b 1
) else (
  call uv sync --all-groups || exit /b 1
)
call npm install --prefix frontend || exit /b 1
call npm run build --prefix frontend || exit /b 1
