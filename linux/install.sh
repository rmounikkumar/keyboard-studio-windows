#!/bin/bash
# Install Keyboard Studio and the CASUE backlight service.
#
#   ./install.sh            user pieces, then pkexec for the system service
#   ./install.sh --system   system pieces only (run as root, internal use)
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/src"
desk="$here/desktop"
app_bin="${HOME:-/root}/.local/bin"

install_user() {
    echo "==> user pieces"
    install -d "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.config/autostart"
    install -m 755 "$src/keyboard-studio" "$HOME/.local/bin/keyboard-studio"
    install -m 755 "$src/keyboard-studio-restore" "$HOME/.local/bin/keyboard-studio-restore"

    sed "s|^Exec=.*|Exec=$HOME/.local/bin/keyboard-studio|" \
        "$desk/keyboard-studio.desktop" > "$HOME/.local/share/applications/keyboard-studio.desktop"
    sed "s|^Exec=.*|Exec=$HOME/.local/bin/keyboard-studio-restore|" \
        "$desk/keyboard-studio-restore.desktop" > "$HOME/.config/autostart/keyboard-studio-restore.desktop"
    chmod 644 "$HOME/.local/share/applications/keyboard-studio.desktop" \
              "$HOME/.config/autostart/keyboard-studio-restore.desktop"
    command -v update-desktop-database >/dev/null && \
        update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    echo "    keyboard-studio, keyboard-studio-restore, menu + autostart entries"
}

install_system() {
    echo "==> system pieces"
    install -m 755 "$src/casue-kbd-backlight" /usr/local/bin/casue-kbd-backlight
    install -m 755 "$src/casue-kbd-effect" /usr/local/bin/casue-kbd-effect
    install -m 644 "$desk/casue-kbd-backlight.service" /etc/systemd/system/casue-kbd-backlight.service
    systemctl daemon-reload
    systemctl enable casue-kbd-backlight >/dev/null 2>&1 || true
    systemctl restart casue-kbd-backlight
    sleep 1
    systemctl is-active casue-kbd-backlight
    echo "    /usr/local/bin/casue-kbd-backlight, /usr/local/bin/casue-kbd-effect, systemd unit"
}

if [ "${1:-}" = "--system" ]; then
    [ "$(id -u)" -eq 0 ] || { echo "run with pkexec or as root" >&2; exit 1; }
    install_system
    exit 0
fi

install_user

if [ "$(id -u)" -eq 0 ]; then
    install_system
else
    echo "==> admin password needed once, for the background service"
    pkexec "$here/install.sh" --system
fi

echo
echo "Done."
echo "  GUI:  Settings -> Keyboard Studio   (or run keyboard-studio)"
echo "  CLI:  casue-kbd-effect [mode]"
echo "  Docs: $here/docs/keyboard-backlight.md"
