#!/usr/bin/env bash
# Build the Bulletin Studio JS app and drop the bundle into the package's static dir.
#
#   ./sync-frontend.sh [path-to-bulletin-studio-js]   (default: ../bulletin-studio-js)
#
# The JS repo's vite config emits unhashed `bulletin-studio.{js,css}`, which is what
# templates/bulletin_studio/app.html loads via {% static %}.
set -euo pipefail

SRC="${1:-../bulletin-studio-js}"
DEST="$(cd "$(dirname "$0")" && pwd)/bulletin_studio/static/bulletin_studio/app"

if [[ -L "$DEST" ]]; then
  echo "$DEST is a symlink (dev setup) - building in place, nothing to copy."
  npm --prefix "$SRC" run build
  exit 0
fi

npm --prefix "$SRC" run build

rm -rf "$DEST"
mkdir -p "$DEST"
cp -r "$SRC/dist/." "$DEST/"
rm -f "$DEST/index.html"   # the Wagtail template is the host page

echo "Synced $(cd "$SRC" && pwd)/dist -> $DEST"
