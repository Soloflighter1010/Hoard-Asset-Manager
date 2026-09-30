#!/usr/bin/env bash
# Put dist/Hoard.app (made by PyInstaller from packaging/hoard.spec) in an installer package:
#   dist/Hoard-<version>-macos-<apple-silicon|intel>.pkg, which installs Hoard in /Applications,
# and dist/SHA256SUMS-macos-<chip>.txt. Run on a Mac, after the PyInstaller build (release.yml and check.yml do).
# The package isn't signed: macOS asks you to allow it once (see the wiki's Installing Hoard page).
set -euo pipefail
cd "$(dirname "$0")/.."
version=$(python3 -c "import re; print(re.search(r'__version__ = \"([^\"]+)\"', open('hoard/__init__.py').read()).group(1))")
case "$(uname -m)" in
  arm64) chip=apple-silicon ;;
  x86_64) chip=intel ;;
  *) echo "Unknown Mac: $(uname -m)" >&2; exit 1 ;;
esac
[ -d dist/Hoard.app ] || { echo "dist/Hoard.app isn't there: build it with PyInstaller first." >&2; exit 1; }

root=$(mktemp -d)
mkdir -p "$root/Applications"
cp -R dist/Hoard.app "$root/Applications/"
# Installed where it says, always: not "relocated" to wherever an older copy was moved.
pkgbuild --analyze --root "$root" "$root.plist"
plutil -replace 0.BundleIsRelocatable -bool NO "$root.plist"
pkg="Hoard-$version-macos-$chip.pkg"
pkgbuild --root "$root" --component-plist "$root.plist" --install-location / \
  --identifier io.github.soloflighter1010.Hoard --version "$version" "dist/$pkg"
rm -rf "$root" "$root.plist"
(cd dist && shasum -a 256 "$pkg" > "SHA256SUMS-macos-$chip.txt")
echo "Built dist/$pkg"
