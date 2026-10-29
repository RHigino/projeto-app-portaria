@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Redefinicao de senha - execute apenas no computador servidor.
echo.
set /p LOGIN=Login do usuario:
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 app.py --redefinir-senha "%LOGIN%"
) else (
    python app.py --redefinir-senha "%LOGIN%"
)
echo.
pause
