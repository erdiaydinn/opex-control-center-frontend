@echo off
REM Pascal editor must live outside frontend to avoid React 18 / React 19 dependency conflicts.
REM Put editor-main folder next to frontend or update PASCAL_DIR below.
set PASCAL_DIR=C:\Users\ErdiAydin\planai\editor-main
if not exist "%PASCAL_DIR%" (
  echo Pascal editor folder not found: %PASCAL_DIR%
  echo Update this script with your editor-main path.
  pause
  exit /b 1
)
cd /d "%PASCAL_DIR%"
bun install
bun run dev
