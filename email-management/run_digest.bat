@echo off
setlocal
REM ===========================================================================
REM  run_digest.bat -- download recent mail, summarize it, narrate it.
REM
REM    run_digest.bat [DAYS]
REM
REM    DAYS   how far back to look. Default: 7
REM
REM  Steps:  imap_download.py  ->  summarize_emails.py  ->  tts_kokoro.py
REM  Set TTS=sapi to narrate with the built-in Windows voices instead (no ML
REM  model download). Set PYTHON to point at a specific interpreter, e.g.
REM  a virtualenv:  set PYTHON=%~dp0.venv\Scripts\python.exe
REM ===========================================================================

cd /d "%~dp0"

set "DAYS=%~1"
if "%DAYS%"=="" set "DAYS=7"

if not defined PYTHON (
    if exist "%~dp0.venv\Scripts\python.exe" (
        set "PYTHON=%~dp0.venv\Scripts\python.exe"
    ) else (
        set "PYTHON=python"
    )
)

if /i "%TTS%"=="sapi" (set "TTS_SCRIPT=tts_sapi.py") else (set "TTS_SCRIPT=tts_kokoro.py")

echo === Step 1/3: Downloading mail from the past %DAYS% day(s) ===
"%PYTHON%" imap_download.py --credentials config\credentials.json --output output --days %DAYS%
if errorlevel 1 goto :error

echo.
echo === Step 2/3: Summarizing with Ollama ===
"%PYTHON%" summarize_emails.py --source output --days %DAYS% --output summary.txt
if errorlevel 1 goto :error

echo.
echo === Step 3/3: Generating speech audio (%TTS_SCRIPT%) ===
"%PYTHON%" %TTS_SCRIPT% --input summary.txt --output summary.mp3
if errorlevel 1 goto :error

echo.
echo All done. Text: summary.txt  Audio: summary.mp3
exit /b 0

:error
echo.
echo A step failed above. Aborting.
exit /b 1
