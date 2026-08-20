#!/bin/bash
# packaging/build_macos.sh — roda no macOS, na raiz do projeto.
set -e

pip3 install -r requirements.txt --quiet
pip3 install pyinstaller --quiet

rm -rf dist/ORVYN.app dist/ORVYN-Master.app
pyinstaller packaging/orvyn.spec --noconfirm
pyinstaller packaging/orvyn_master.spec --noconfirm

mkdir -p dist_installers

if ! command -v create-dmg >/dev/null 2>&1; then
    echo "create-dmg não encontrado. Instale com: brew install create-dmg"
    exit 1
fi

create-dmg \
  --volname "ORVYN" \
  --window-size 500 300 \
  --icon "ORVYN.app" 120 120 \
  --app-drop-link 360 120 \
  "dist_installers/ORVYN-Installer.dmg" \
  "dist/ORVYN.app"

echo "Instalador gerado em dist_installers/ORVYN-Installer.dmg"
