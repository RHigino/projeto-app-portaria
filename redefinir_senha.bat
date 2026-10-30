@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Redefinicao de senha - use em um computador com acesso a pasta do banco.
echo.
set /p LOGIN=Login do usuario:
if exist PrevencaoPerdas.exe (
    PrevencaoPerdas.exe --redefinir-senha "%LOGIN%"
) else (
    where py >nul 2>nul
    if errorlevel 1 (
        python app.py --redefinir-senha "%LOGIN%"
    ) else (
        py -3 app.py --redefinir-senha "%LOGIN%"
    )
)
echo.
pause
