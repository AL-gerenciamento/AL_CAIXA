#!/bin/bash
# packaging/build_macos.sh — roda no macOS, na raiz do projeto.
set -e

pip3 install -r requirements.txt --quiet
pip3 install pyinstaller --quiet

rm -rf dist/AL Caixa.app dist/ALGL mercado.app
pyinstaller packaging/al_caixa.spec --noconfirm
pyinstaller packaging/al_gerenciamento_master.spec --noconfirm

mkdir -p dist_installers

if ! command -v create-dmg >/dev/null 2>&1; then
    echo "create-dmg não encontrado. Instale com: brew install create-dmg"
    exit 1
fi

create-dmg \
  --volname "AL Caixa" \
  --window-size 500 300 \
  --icon "AL Caixa.app" 120 120 \
  --app-drop-link 360 120 \
  "dist_installers/AL-Caixa-Installer.dmg" \
  "dist/AL Caixa.app"

echo "Instalador gerado em dist_installers/AL-Caixa-Installer.dmg"
