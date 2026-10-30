@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Gerando PrevencaoPerdas.exe (requer Python e PyInstaller nesta maquina)...
py -3 -m PyInstaller --noconfirm --clean --onefile --name PrevencaoPerdas --icon icone.ico ^
  --add-data "schema.json;." --add-data "static;static" iniciar.py
if errorlevel 1 (
    echo.
    echo Falhou. Instale o PyInstaller com: py -3 -m pip install pyinstaller
) else (
    copy /y redefinir_senha.bat dist\ >nul
    echo.
    echo Pronto: dist\PrevencaoPerdas.exe
)
pause
