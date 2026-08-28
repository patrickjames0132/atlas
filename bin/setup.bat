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

rem The heavy capabilities are optional extras since v7.15.0; a local bootstrap
rem installs all of them. ATLAS_SKIP_TORCH=1 drops the `sources` extra, which is
rem where torch lives -- see setup.sh for the full story. CI runs the .sh under
rem bash on both runners, so this branch exists for parity, not because CI uses
rem it. Don't set it locally: `atlas serve` needs torch to embed anything.
if "%ATLAS_SKIP_TORCH%"=="1" (
  call uv sync --all-groups --extra pdf --extra corpus || exit /b 1
) else (
  call uv sync --all-groups --extra pdf --extra corpus --extra sources || exit /b 1
)
call npm install --prefix frontend || exit /b 1
call npm run build --prefix frontend || exit /b 1
