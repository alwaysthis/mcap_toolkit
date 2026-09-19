@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>&1
if errorlevel 1 (
    echo uv is not installed.
    echo Install: https://docs.astral.sh/uv/getting-started/installation/
    pause
    exit /b 1
)

uv sync
if errorlevel 1 (
    echo uv sync failed.
    pause
    exit /b 1
)

uv run python -m mcap_toolkit %*
if errorlevel 1 (
    echo.
    echo mcap_toolkit exited with an error.
    pause
    exit /b 1
)
