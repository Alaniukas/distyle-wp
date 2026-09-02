@echo off
REM Apply 10 sofų — TIKRAS atnaujinimas distyle.lt
echo WARNING: This will update product images on distyle.lt!
pause
cd /d "%~dp0client"
call .venv\Scripts\activate
python -m distyle_photo run --apply --limit 10 --category 21 --skip-on-sale --non-standard-only --skip-processed
pause
