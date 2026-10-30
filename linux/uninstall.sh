#!/bin/bash
# Remove Keyboard Studio and the CASUE backlight service.
#
#   ./uninstall.sh            user pieces, then pkexec for the system service
#   ./uninstall.sh --system   system pieces only (run as root, internal use)
set -euo pipefail

remove_user() {
    echo "==> user pieces"
    rm -f "$HOME/.local/bin/keyboard-studio" \
          "$HOME/.local/bin/keyboard-studio-restore" \
          "$HOME/.local/share/applications/keyboard-studio.desktop" \
          "$HOME/.config/autostart/keyboard-studio-restore.desktop"
    rm -rf "$HOME/.config/keyboard-studio"
    command -v update-desktop-database >/dev/null && \
        update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
}

remove_system() {
    echo "==> system pieces"
    systemctl disable --now casue-kbd-backlight 2>/dev/null || true
    rm -f /etc/systemd/system/casue-kbd-backlight.service \
          /usr/local/bin/casue-kbd-backlight \
          /usr/local/bin/casue-kbd-effect \
          /run/casue-kbd-effect \
          /run/casue-kbd-params \
          /var/log/casue-kbd-backlight.log
    systemctl daemon-reload
    # hand the strip back to a plain on state
    for p in /sys/class/leds/*::scrolllock/brightness; do
        case "$(readlink -f "$p" 2>/dev/null | tr 'a-z' 'A-Z')" in
            *2A7A:959F*) echo 1 > "$p" 2>/dev/null || true ;;
        esac
    done
}

if [ "${1:-}" = "--system" ]; then
    [ "$(id -u)" -eq 0 ] || { echo "run with pkexec or as root" >&2; exit 1; }
    remove_system
    exit 0
fi

remove_user
if [ "$(id -u)" -eq 0 ]; then
    remove_system
else
    echo "==> admin password needed once, to remove the service"
    pkexec "$(cd "$(dirname "$0")" && pwd)/uninstall.sh" --system || true
fi
echo "Removed. The keyboard light stays in whatever state it is in now."
