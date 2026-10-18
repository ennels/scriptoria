#!/usr/bin/env bash
# Install Scriptoria launchers (Linux, XDG): an app-menu entry and a desktop icon.
# Both start the local server and open the reader. Safe to re-run any time.
#
#   bash scripts/install-launcher.sh               # menu entry + desktop icon
#   bash scripts/install-launcher.sh --no-desktop  # menu entry only
set -euo pipefail

DESKTOP_ICON=1
[ "${1:-}" = "--no-desktop" ] && DESKTOP_ICON=0

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPS="$HOME/.local/share/applications"
BIN="$HOME/.local/bin"
ICONS="$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$APPS" "$BIN" "$ICONS"

# Find uv even when it isn't on PATH (menu and desktop launches get a minimal PATH).
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

# Icon goes into the user's icon theme, so the launcher survives the repo moving.
cp "$ROOT/scripts/scriptoria.svg" "$ICONS/scriptoria.svg"
gtk-update-icon-cache -q -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

cat > "$APPS/scriptoria.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Scriptoria
GenericName=Bible Study
Comment=Offline Bible study — parallel translations, Hebrew & Greek, word studies, notes
Exec=$BIN/scriptoria
Icon=scriptoria
Terminal=false
StartupNotify=false
Categories=Education;Literature;
Keywords=bible;scripture;greek;hebrew;interlinear;study;
EOF
chmod +x "$APPS/scriptoria.desktop"
update-desktop-database "$APPS" 2>/dev/null || true

echo "Installed Scriptoria."
echo "  app menu : $APPS/scriptoria.desktop"

if [ "$DESKTOP_ICON" = 1 ]; then
  DESK="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
  [ -z "$DESK" ] && DESK="$HOME/Desktop"
  if [ "$DESK" != "$HOME" ] && mkdir -p "$DESK" 2>/dev/null; then
    install -m 755 "$APPS/scriptoria.desktop" "$DESK/scriptoria.desktop"
    # GNOME only launches desktop files it has been told to trust.
    gio set "$DESK/scriptoria.desktop" metadata::trusted true 2>/dev/null || true
    echo "  desktop  : $DESK/scriptoria.desktop"
    echo "  (If the icon shows a warning badge, right-click it and choose \"Allow Launching\".)"
  fi
fi
echo "Or run: scriptoria"
