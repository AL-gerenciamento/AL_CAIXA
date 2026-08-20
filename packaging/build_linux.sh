#!/bin/bash
# packaging/build_linux.sh — roda no Linux, na raiz do projeto.
set -e

pip3 install -r requirements.txt --quiet
pip3 install pyinstaller --quiet

rm -rf dist/ORVYN dist/ORVYN-Master
pyinstaller packaging/orvyn.spec --noconfirm
pyinstaller packaging/orvyn_master.spec --noconfirm

mkdir -p dist_installers/AppDir/usr/bin
cp dist/ORVYN dist_installers/AppDir/usr/bin/ORVYN
chmod +x dist_installers/AppDir/usr/bin/ORVYN

mkdir -p dist_installers/AppDir/usr/share/applications
cat > dist_installers/AppDir/usr/share/applications/orvyn.desktop <<EOF
[Desktop Entry]
Name=ORVYN
Exec=ORVYN
Icon=orvyn
Type=Application
Categories=Office;Finance;
EOF

mkdir -p dist_installers/AppDir/usr/share/icons/hicolor/256x256/apps
cp assets/icons/orvyn.png dist_installers/AppDir/usr/share/icons/hicolor/256x256/apps/orvyn.png 2>/dev/null || true
ln -sf usr/share/icons/hicolor/256x256/apps/orvyn.png dist_installers/AppDir/orvyn.png
ln -sf usr/share/applications/orvyn.desktop dist_installers/AppDir/orvyn.desktop
ln -sf usr/bin/ORVYN dist_installers/AppDir/AppRun

if [ ! -f appimagetool ]; then
    wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" -O appimagetool
    chmod +x appimagetool
fi

./appimagetool dist_installers/AppDir dist_installers/ORVYN-x86_64.AppImage
echo "Instalador gerado em dist_installers/ORVYN-x86_64.AppImage"
