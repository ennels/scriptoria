#!/usr/bin/env bash
# Install a "Scriptoria" desktop launcher (Linux, XDG). Starts the local server
# and opens the reader. Re-run any time; it just rewrites the entry.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPS="$HOME/.local/share/applications"
BIN="$HOME/.local/bin"
mkdir -p "$APPS" "$BIN"

# Wrapper: run from the project dir so uv finds the venv + database.
cat > "$BIN/scriptoria" <<EOF
#!/usr/bin/env bash
cd "$ROOT"
exec uv run scriptoria
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
