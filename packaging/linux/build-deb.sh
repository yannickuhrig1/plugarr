#!/usr/bin/env bash
# Build the Debian package from the PyInstaller onedir bundle.
#
# Usage:
#   packaging/linux/build-deb.sh <PlugArr-directory> <version> <output-directory>
#
# The bundle is deliberately copied below /opt instead of rebuilt during package
# installation.  A PlugArr release must stay runnable without Python, pip or an
# Internet connection on the target machine.
set -euo pipefail

source_dir=${1:?"PyInstaller directory required"}
version=${2:?"version required"}
output_dir=${3:?"output directory required"}

case "$version" in
  ''|*[!0-9.]*|.*|*.) echo "Invalid Debian version: $version" >&2; exit 2 ;;
esac
command -v dpkg-deb >/dev/null || { echo "dpkg-deb is required" >&2; exit 2; }
test -x "$source_dir/plugarr" || { echo "plugarr missing from $source_dir" >&2; exit 2; }
test -x "$source_dir/plugarr-admin" || { echo "plugarr-admin missing from $source_dir" >&2; exit 2; }
test -d "$source_dir/_internal" || { echo "shared _internal runtime missing" >&2; exit 2; }

root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT
mkdir -p "$root/DEBIAN" "$root/opt/plugarr" \
  "$root/usr/bin" "$root/usr/share/applications" \
  "$root/usr/share/icons/hicolor/scalable/apps"

cp -a "$source_dir/." "$root/opt/plugarr/"
ln -s /opt/plugarr/plugarr "$root/usr/bin/plugarr"
ln -s /opt/plugarr/plugarr-admin "$root/usr/bin/plugarr-admin"
install -m 0644 packaging/linux/plugarr-admin.desktop \
  "$root/usr/share/applications/plugarr-admin.desktop"
install -m 0644 assets/plugarr-mark.svg \
  "$root/usr/share/icons/hicolor/scalable/apps/plugarr.svg"

cat > "$root/DEBIAN/control" <<EOF
Package: plugarr
Version: $version
Section: utils
Priority: optional
Architecture: amd64
Maintainer: PlugArr contributors <noreply@github.com>
Depends: libc6 (>= 2.35)
Description: Deploy and wire a media Docker stack
 PlugArr creates, wires and verifies a Docker media stack. This package contains
 the command-line wizard and the local PlugArr Administration launcher.
EOF

mkdir -p "$output_dir"
dpkg-deb --root-owner-group --build "$root" "$output_dir/plugarr_${version}_amd64.deb"
