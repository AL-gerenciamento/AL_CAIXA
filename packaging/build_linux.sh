#!/bin/bash
# packaging/build_linux.sh — roda no Linux, na raiz do projeto.
set -e

pip3 install -r requirements.txt --quiet
pip3 install pyinstaller --quiet

rm -rf dist/AL Caixa dist/ALGL mercado
pyinstaller packaging/al_caixa.spec --noconfirm
pyinstaller packaging/al_gerenciamento_master.spec --noconfirm

mkdir -p dist_installers/AppDir/usr/bin
cp "dist/AL Caixa" dist_installers/AppDir/usr/bin/AL-Caixa
chmod +x dist_installers/AppDir/usr/bin/AL-Caixa

mkdir -p dist_installers/AppDir/usr/share/applications
cat > dist_installers/AppDir/usr/share/applications/al-caixa.desktop <<EOF
[Desktop Entry]
Name=AL Caixa
Exec=AL-Caixa
Icon=al-caixa
Type=Application
Categories=Office;Finance;
EOF

mkdir -p dist_installers/AppDir/usr/share/icons/hicolor/256x256/apps
cp assets/icons/al-caixa.png dist_installers/AppDir/usr/share/icons/hicolor/256x256/apps/al-caixa.png 2>/dev/null || true
ln -sf usr/share/icons/hicolor/256x256/apps/al-caixa.png dist_installers/AppDir/al-caixa.png
ln -sf usr/share/applications/al-caixa.desktop dist_installers/AppDir/al-caixa.desktop
ln -sf usr/bin/AL-Caixa dist_installers/AppDir/AppRun

if [ ! -f appimagetool ]; then
    wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" -O appimagetool
    chmod +x appimagetool
fi

./appimagetool dist_installers/AppDir dist_installers/AL-Caixa-x86_64.AppImage
echo "Instalador gerado em dist_installers/AL-Caixa-x86_64.AppImage"
