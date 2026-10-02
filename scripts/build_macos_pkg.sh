#!/usr/bin/env bash
# Put dist/Hoard.app (made by PyInstaller from packaging/hoard.spec) in an installer package:
#   dist/Hoard-<version>-macos-<apple-silicon|intel>.pkg, which installs Hoard in /Applications,
# and dist/SHA256SUMS-macos-<chip>.txt. Run on a Mac, after the PyInstaller build (release.yml and check.yml do).
# The package isn't signed: macOS asks you to allow it once (see the wiki's Installing Hoard page).
set -euo pipefail
cd "$(dirname "$0")/.."
version=$(python3 -c "import re; print(re.search(r'__version__ = \"([^\"]+)\"', open('hoard/__init__.py').read()).group(1))")
numbers=$(python3 -c "import re, sys; print('.'.join(re.findall(r'\d+', sys.argv[1])[:3]))" "$version")   # a beta's 3.1.0
case "$(uname -m)" in
  arm64) chip=apple-silicon ;;
  x86_64) chip=intel ;;
  *) echo "Unknown Mac: $(uname -m)" >&2; exit 1 ;;
esac
[ -d dist/Hoard.app ] || { echo "dist/Hoard.app isn't there: build it with PyInstaller first." >&2; exit 1; }

root=$(mktemp -d)
mkdir -p "$root/Applications"
cp -R dist/Hoard.app "$root/Applications/"
pkgbuild --analyze --root "$root" "$root.plist"
# Every bundle in it (Hoard.app, and the Python.framework inside it) is installed exactly where it says: never
# "relocated" onto another copy with the same identifier, such as python.org's Python in /Library/Frameworks.
i=0
while plutil -extract "$i" xml1 -o /dev/null "$root.plist" 2>/dev/null; do
  plutil -replace "$i.BundleIsRelocatable" -bool NO "$root.plist"
  i=$((i + 1))
done
[ "$i" -gt 0 ] || { echo "pkgbuild found no bundles in $root" >&2; exit 1; }
pkg="Hoard-$version-macos-$chip.pkg"
pkgbuild --root "$root" --component-plist "$root.plist" --install-location / \
  --identifier io.github.soloflighter1010.Hoard --version "$numbers" "dist/$pkg"
rm -rf "$root" "$root.plist"
# Check it: the package's own record lists no bundle Installer may relocate.
pkgutil --expand "dist/$pkg" "$root.check"
if grep -A20 "<relocate" "$root.check/PackageInfo" | grep -q "<bundle"; then
  echo "dist/$pkg still has relocatable bundles" >&2; exit 1
fi
rm -rf "$root.check"
(cd dist && shasum -a 256 "$pkg" > "SHA256SUMS-macos-$chip.txt")
echo "Built dist/$pkg"
