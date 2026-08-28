@echo off
setlocal enabledelayedexpansion
REM ===========================================================================
REM  run_audit.bat -- inbox audit, end to end.
REM
REM    run_audit.bat [MAIL_FOLDER] [OUTPUT_FOLDER]
REM
REM    MAIL_FOLDER    folder of .eml files. Default: .\output relative to this
REM                   script. Subfolders are walked too.
REM    OUTPUT_FOLDER  where everything lands. Default: .\audit_out
REM
REM  config\aliases.json and config\annotations.json are used when present and
REM  skipped when absent -- neither is required.
REM
REM  Produces OUTPUT_FOLDER\inbox_audit.html plus the intermediate data.
REM  Set NO_OPEN=1 to skip opening the report in a browser.
REM ===========================================================================

set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

set "MAILDIR=%~1"
if "%MAILDIR%"=="" set "MAILDIR=%HERE%\output"
set "OUTDIR=%~2"
if "%OUTDIR%"=="" set "OUTDIR=%HERE%\audit_out"

REM --- locate a Python 3 -----------------------------------------------------
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo ERROR: no Python found on PATH. Install Python 3 and try again.
  exit /b 1
)

if not exist "%MAILDIR%" (
  echo ERROR: mail folder not found: "%MAILDIR%"
  echo Usage: run_audit.bat [MAIL_FOLDER] [OUTPUT_FOLDER]
  exit /b 1
)
if not exist "%OUTDIR%" mkdir "%OUTDIR%"

REM --- optional configuration ------------------------------------------------
set "ALIASES="
if exist "%HERE%\config\aliases.json" set "ALIASES=--config "%HERE%\config\aliases.json""
set "NOTES="
if exist "%HERE%\config\annotations.json" set "NOTES=--annotations "%HERE%\config\annotations.json""

echo.
echo   source : %MAILDIR%
echo   output : %OUTDIR%
echo   python : %PY%
echo.

REM --- stage 1: .eml -> messages.jsonl ---------------------------------------
%PY% "%HERE%\eml_extract.py" "%MAILDIR%" -o "%OUTDIR%\messages.jsonl"
if errorlevel 1 goto :failed

REM --- stage 1.5: regroup sending identities ---------------------------------
%PY% "%HERE%\sender_groups.py" "%OUTDIR%\messages.jsonl" ^
     -o "%OUTDIR%\messages_grouped.jsonl" ^
     %ALIASES% ^
     --emit-domain-aliases "%OUTDIR%\_domain_aliases.json"
if errorlevel 1 goto :failed

REM --- stage 2: score registration + build the cleanup plan ------------------
%PY% "%HERE%\inbox_summary.py" "%OUTDIR%\messages_grouped.jsonl" ^
     --outdir "%OUTDIR%\report" ^
     --aliases "%OUTDIR%\_domain_aliases.json"
if errorlevel 1 goto :failed

REM --- stage 3: ordered work list --------------------------------------------
%PY% "%HERE%\worklist.py" "%OUTDIR%\report\summary.json" ^
     -o "%OUTDIR%\inbox_cleanup_worklist.csv" ^
     --json "%OUTDIR%\worklist.json" ^
     %NOTES%
if errorlevel 1 goto :failed

REM --- stage 4: the report ----------------------------------------------------
%PY% "%HERE%\gen_report.py" "%OUTDIR%\report\summary.json" "%OUTDIR%\worklist.json" ^
     -o "%OUTDIR%\inbox_audit.html" ^
     %NOTES% ^
     --source "%MAILDIR%"
if errorlevel 1 goto :failed

echo.
echo   DONE  %OUTDIR%\inbox_audit.html
echo         %OUTDIR%\inbox_cleanup_worklist.csv
echo.
if /i not "%NO_OPEN%"=="1" start "" "%OUTDIR%\inbox_audit.html"
exit /b 0

:failed
echo.
echo   FAILED at the step above. Nothing further was run.
exit /b 1
