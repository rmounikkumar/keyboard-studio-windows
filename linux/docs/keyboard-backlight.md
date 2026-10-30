## CASUE USB keyboard RGB backlight (2026-10-30)

**Symptom:** external "CASUE USB KB" (USB `2a7a:959f`) had RGB lighting that never
turned on under Linux, while every key worked.

**Cause:** the keyboard's firmware uses the **ScrollLock LED bit** as its lighting
enable. Its HID descriptor exposes only the standard LED report
(`NumLock`, `CapsLock`, `ScrollLock`, `Compose`, `Kana`) — no vendor RGB report
and no OUT endpoint — so nothing in Linux ever set ScrollLock and the light
stayed dark. Verified bit by bit: only `inputN::scrolllock` switches it on.

**Fix:** `/usr/local/bin/casue-kbd-backlight` (root, Python) +
`/etc/systemd/system/casue-kbd-backlight.service`, enabled at boot.

- Light comes on at login.
- **Scroll Lock is the on/off switch** for the backlight (the service reads
  `KEY_SCROLLLOCK` from the keyboard directly and flips the LED bit).
- KDE rewrites the whole LED mask on Caps Lock / Num Lock, which used to clear
  the bit; the service puts it straight back (inotify, ~0.1 ms, plus a 1 s
  safety sweep), so the light does not blink.
- Finds the keyboard by USB ID (`2A7A:959F`) and re-scans, so replug and
  re-enumeration are handled automatically.

**Effects:** the strip is binary (on/off only — the hardware has no colour
control), so every effect is a blink pattern:

| mode | what it does |
|------|--------------|
| `steady` | plain on/off, toggled by Scroll Lock (boot default) |
| `off` | light stays off |
| `slow` | 4 s on, 4 s off |
| `pulse` | slow breathing, 3.2 s cycle |
| `breathe` | faster breathing, 1.6 s cycle |
| `aurora` | drifting swells, 0.4-1.7 s, no fixed beat |
| `heartbeat` | double beat, 1.25 s cycle |
| `strobe` | fast 8 Hz flicker (photosensitivity warning) |
| `candle` | random soft flicker |
| `sos` | Morse ... --- ... repeating |
| `typing` | lights up while you type, fades out 1.2 s after the last key |
| `cpu` | blink duty cycle follows CPU load |
| `disk` | flickers while the disk is busy |
| `net` | flickers while the network is busy |

```bash
casue-kbd-effect            # show current mode + list
casue-kbd-effect sos        # pick a mode (no sudo needed)
```

**Keyboard Studio (GUI):** `~/.local/bin/keyboard-studio` — a Qt6 app with a
14-effect grid, a live mini-keyboard preview, and a speed slider (0.25×–4×).
Menu entry: *Settings → Keyboard Studio*. It writes the same two runtime files,
so no sudo is needed, and it saves the last choice to
`~/.config/keyboard-studio/state.json`. `keyboard-studio-restore` (autostart,
`~/.config/autostart/keyboard-studio-restore.desktop`) reapplies that choice at
login.


**Firmware modes:** the board also has its own lighting modes (wave, twinkle,
etc.) triggered from the keyboard itself with the light/Fn key combo. Those are
drawn by the firmware, so keep the service on `steady` while using one — the
`pulse`/`strobe`/etc. effects cut power rhythmically and would break the
firmware animation.

Boot default is `steady` (light on). Pressing Scroll Lock in any effect jumps
back to `steady` with the light on, then keeps toggling it.

Check:
```bash
systemctl status casue-kbd-backlight.service
cat /sys/class/leds/input*::scrolllock/brightness   # CASUE one: 1 = lit
tail /var/log/casue-kbd-backlight.log               # switch events
```

Remove the fix entirely:
```bash
sudo systemctl disable --now casue-kbd-backlight
sudo rm /etc/systemd/system/casue-kbd-backlight.service /usr/local/bin/casue-kbd-backlight /var/log/casue-kbd-backlight.log
sudo systemctl daemon-reload
```
