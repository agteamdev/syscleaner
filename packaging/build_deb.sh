#!/usr/bin/env bash
# Сборка .deb:  ./packaging/build_deb.sh  ->  dist/syscleaner_<ver>_all.deb
set -euo pipefail
cd "$(dirname "$0")/.."
VER=$(python3 -c "import syscleaner; print(syscleaner.__version__)")
PKG=build/syscleaner_${VER}_all
rm -rf "$PKG"; mkdir -p dist
mkdir -p "$PKG/DEBIAN" "$PKG/usr/bin" "$PKG/usr/lib/syscleaner" \
         "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/scalable/apps" \
         "$PKG/usr/share/doc/syscleaner"

cp -r syscleaner "$PKG/usr/lib/syscleaner/"
find "$PKG" -name __pycache__ -type d -prune -exec rm -rf {} +

cat > "$PKG/usr/bin/syscleaner" <<'WRAP'
#!/bin/sh
exec env PYTHONPATH=/usr/lib/syscleaner python3 -m syscleaner "$@"
WRAP
chmod 755 "$PKG/usr/bin/syscleaner"

install -m644 packaging/syscleaner.desktop "$PKG/usr/share/applications/syscleaner.desktop"
install -m644 packaging/syscleaner.svg "$PKG/usr/share/icons/hicolor/scalable/apps/syscleaner.svg"
install -m644 LICENSE "$PKG/usr/share/doc/syscleaner/copyright"

cat > "$PKG/DEBIAN/control" <<CTL
Package: syscleaner
Version: $VER
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-gi, gir1.2-gtk-3.0, python3-yaml, policykit-1 | pkexec
Recommends: deborphan
Maintainer: agteamdev <noreply@users.noreply.github.com>
Homepage: https://github.com/agteamdev/syscleaner
Description: GUI-очистка и диагностика Linux Mint / Debian
 Выбор задач, описания и уровни риска, предпросмотр с оценкой размера,
 просмотр занятого места, лог в реальном времени и расписание (systemd timer).
CTL

cat > "$PKG/DEBIAN/postinst" <<'PST'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null && update-desktop-database -q || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t /usr/share/icons/hicolor 2>/dev/null || true
exit 0
PST
chmod 755 "$PKG/DEBIAN/postinst"

cat > "$PKG/DEBIAN/postrm" <<'PRM'
#!/bin/sh
set -e
if [ "$1" = "purge" ] || [ "$1" = "remove" ]; then
  systemctl disable --now syscleaner.timer 2>/dev/null || true
  rm -f /etc/systemd/system/syscleaner.timer /etc/systemd/system/syscleaner.service
  [ "$1" = "purge" ] && rm -rf /etc/syscleaner || true
  systemctl daemon-reload 2>/dev/null || true
fi
exit 0
PRM
chmod 755 "$PKG/DEBIAN/postrm"

dpkg-deb --build --root-owner-group "$PKG" "dist/syscleaner_${VER}_all.deb"
echo "Готово: dist/syscleaner_${VER}_all.deb"
