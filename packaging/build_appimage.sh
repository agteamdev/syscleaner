#!/usr/bin/env bash
# Сборка AppImage:  ./packaging/build_appimage.sh  ->  dist/SysCleaner-<ver>-x86_64.AppImage
# Нужен интернет один раз (скачивается appimagetool) либо переменная APPIMAGETOOL=/путь/к/appimagetool.
set -euo pipefail
cd "$(dirname "$0")/.."
VER=$(python3 -c "import syscleaner; print(syscleaner.__version__)")
APPDIR=build/AppDir
rm -rf "$APPDIR"; mkdir -p dist build "$APPDIR/usr/lib/syscleaner"

cp -r syscleaner "$APPDIR/usr/lib/syscleaner/"
find "$APPDIR" -name __pycache__ -type d -prune -exec rm -rf {} +
install -m755 packaging/AppRun "$APPDIR/AppRun"
install -m644 packaging/syscleaner.desktop "$APPDIR/syscleaner.desktop"
install -m644 packaging/syscleaner.svg "$APPDIR/syscleaner.svg"
cp "$APPDIR/syscleaner.svg" "$APPDIR/.DirIcon"

TOOL="${APPIMAGETOOL:-build/appimagetool}"
if [ ! -x "$TOOL" ]; then
  echo "Скачиваю appimagetool…"
  curl -fL -o build/appimagetool \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x build/appimagetool
  TOOL=build/appimagetool
fi

ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" "dist/SysCleaner-${VER}-x86_64.AppImage"
echo "Готово: dist/SysCleaner-${VER}-x86_64.AppImage"
