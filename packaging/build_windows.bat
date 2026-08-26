@echo off
REM packaging\build_windows.bat — roda no Windows, na raiz do projeto.
setlocal

cd /d "%~dp0.."

python -m pip install -r requirements.txt --quiet
python -m pip install pyinstaller --quiet

del /q "dist\AL Caixa.exe" "dist\ALGL mercado.exe" 2>nul
python -m PyInstaller packaging\al_caixa.spec --noconfirm
python -m PyInstaller packaging\al_gerenciamento_master.spec --noconfirm

where ISCC >nul 2>nul
if %errorlevel%==0 (
    mkdir dist_installers 2>nul
    ISCC packaging\al_caixa_installer.iss
    ISCC packaging\superadmin_installer.iss
    echo Instaladores gerados em dist_installers\AL-Caixa-Setup.exe e dist_installers\ALGL-mercado-Setup.exe
) else (
    echo Inno Setup [ISCC] nao encontrado no PATH.
    echo Instale em https://jrsoftware.org/isdl.php e rode este script de novo,
    echo ou compile manualmente os arquivos .iss pela interface do Inno Setup.
)

endlocal