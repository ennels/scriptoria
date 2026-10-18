#!/usr/bin/env bash
# Install a "Scriptoria" desktop launcher (Linux, XDG). Starts the local server
# and opens the reader. Re-run any time; it just rewrites the entry.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPS="$HOME/.local/share/applications"
BIN="$HOME/.local/bin"
mkdir -p "$APPS" "$BIN"

# Find uv even when it isn't on PATH (app-menu launches get a minimal PATH).
UV="$(command -v uv || true)"
for p in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" /usr/local/bin/uv /opt/homebrew/bin/uv; do
  [ -z "$UV" ] && [ -x "$p" ] && UV="$p"
done
if [ -z "$UV" ]; then
  echo "uv isn't installed. Install it, then re-run this script:"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

# Wrapper: run from the project dir so uv finds the venv + database.
cat > "$BIN/scriptoria" <<EOF
#!/usr/bin/env bash
cd "$ROOT"
exec "$UV" run scriptoria
EOF
chmod +x "$BIN/scriptoria"

cat > "$APPS/scriptoria.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Scriptoria
Comment=Offline Bible study — parallel translations, Greek/Hebrew, cross-references
Exec=$BIN/scriptoria
Icon=$ROOT/scripts/scriptoria.svg
Terminal=false
Categories=Education;Literature;
Keywords=bible;scripture;greek;hebrew;study;
EOF

update-desktop-database "$APPS" 2>/dev/null || true

echo "Installed Scriptoria launcher."
echo "  menu entry : $APPS/scriptoria.desktop"
echo "  command    : $BIN/scriptoria   (ensure $BIN is on your PATH)"
echo "Launch it from your app menu, or run: scriptoria"
