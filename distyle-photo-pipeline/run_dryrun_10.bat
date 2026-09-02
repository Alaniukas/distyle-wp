@echo off
REM Dry-run 10 sofų — nieko nekeičia svetainėje
cd /d "%~dp0client"
call .venv\Scripts\activate
python -m distyle_photo run --dry-run --limit 10 --category 21 --skip-on-sale --non-standard-only
pause
