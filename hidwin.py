"""Windows HID access for the CASUE USB KB (VID 2A7A / PID 959F).

The strip is powered by the ScrollLock LED bit. There are two ways to drive it
on Windows:

* **Keyboard device interface (primary).** Each keyboard registers a
  `GUID_DEVINTERFACE_KEYBOARD` handle. Windows' own `kbdclass` driver handles
  `IOCTL_KEYBOARD_SET_INDICATORS` on that handle, which is exactly what Windows
  does when it updates the ScrollLock/NumLock/CapsLock lights. Because the
  handle belongs to one keyboard, the app can drive the CASUE without touching
  a laptop's internal keyboard, and it changes only the ScrollLock bit.
* **HID output report (fallback).** `HidD_SetOutputReport` on the keyboard
  collection, plus `WriteFile` if the driver accepts interrupt OUT.

This module:

* enumerates the CASUE's keyboard interface and opens it read/write or
  write-only as available,
* falls back to enumerating the HID interfaces belonging to 2A7A:959F,
* remembers which path the driver accepted,
* reports what actually happened through `diagnose()`.

`diagnose()` returns a plain-text report so the app can show what the machine
really did instead of guessing.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes as wt

if sys.platform != "win32":
    raise ImportError("hidwin is Windows-only")

hid = ctypes.WinDLL("hid.dll", use_last_error=True)
setupapi = ctypes.WinDLL("setupapi.dll", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
user32 = ctypes.WinDLL("user32.dll", use_last_error=True)

user32.GetKeyState.argtypes = [ctypes.c_int]
user32.GetKeyState.restype = ctypes.c_short

VK_CAPITAL = 0x14
VK_NUMLOCK = 0x90

VENDOR_ID = 0x2A7A
PRODUCT_ID = 0x095F
LED_SCROLLLOCK = 0x04          # standard boot-keyboard LED byte, bit 2

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x1
FILE_SHARE_WRITE = 0x2
OPEN_EXISTING = 3
DIGCF_PRESENT = 0x2
DIGCF_DEVICEINTERFACE = 0x10
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

# Keyboard class driver IOCTLs. Windows uses these for the lock indicators.
# They work on the keyboard's own GUID_DEVINTERFACE_KEYBOARD handle, so the app
# can target the CASUE keyboard without touching a laptop's internal keyboard.
FILE_DEVICE_KEYBOARD = 0x0B
IOCTL_KEYBOARD_SET_INDICATORS = 0xB0008
IOCTL_KEYBOARD_QUERY_INDICATORS = 0xB0040
KEYBOARD_SCROLL_LOCK_ON = 0x0001
KEYBOARD_NUM_LOCK_ON = 0x0002
KEYBOARD_CAPS_LOCK_ON = 0x0004

# GUID_DEVINTERFACE_KEYBOARD {884b96c3-56ef-11d1-bc8c-00a0c91405dd}
KEYBOARD_INTERFACE_GUID = (0x884B96C3, 0x56EF, 0x11D1,
                           (0xBC, 0x8C, 0x00, 0xA0, 0xC9, 0x14, 0x05, 0xDD))


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("InterfaceClassGuid", GUID),
                ("Flags", wt.DWORD), ("Reserved", ctypes.c_void_p)]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Size", wt.ULONG), ("VendorID", wt.USHORT),
                ("ProductID", wt.USHORT), ("VersionNumber", wt.USHORT)]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [("Usage", wt.USHORT), ("UsagePage", wt.USHORT),
                ("InputReportByteLength", wt.USHORT),
                ("OutputReportByteLength", wt.USHORT),
                ("FeatureReportByteLength", wt.USHORT),
                ("Reserved", wt.USHORT * 17),
                ("NumberLinkCollectionNodes", wt.USHORT),
                ("NumberInputButtonCaps", wt.USHORT),
                ("NumberInputValueCaps", wt.USHORT),
                ("NumberInputDataIndices", wt.USHORT),
                ("NumberOutputButtonCaps", wt.USHORT),
                ("NumberOutputValueCaps", wt.USHORT),
                ("NumberOutputDataIndices", wt.USHORT),
                ("NumberFeatureButtonCaps", wt.USHORT),
                ("NumberFeatureValueCaps", wt.USHORT),
                ("NumberFeatureDataIndices", wt.USHORT)]


hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
hid.HidD_GetHidGuid.restype = None

hid.HidD_GetAttributes.argtypes = [wt.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
hid.HidD_GetAttributes.restype = wt.BOOL

hid.HidD_GetProductString.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.ULONG]
hid.HidD_GetProductString.restype = wt.BOOL

hid.HidD_GetPreparsedData.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
hid.HidD_GetPreparsedData.restype = wt.BOOL

hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
hid.HidD_FreePreparsedData.restype = wt.BOOL

hid.HidD_SetOutputReport.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.ULONG]
hid.HidD_SetOutputReport.restype = wt.BOOL

hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
hid.HidP_GetCaps.restype = wt.LONG

setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wt.LPCWSTR,
                                         wt.HWND, wt.DWORD]
setupapi.SetupDiGetClassDevsW.restype = wt.HANDLE

setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(GUID), wt.DWORD,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
setupapi.SetupDiEnumDeviceInterfaces.restype = wt.BOOL

setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    wt.HANDLE, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA), ctypes.c_void_p,
    wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wt.BOOL

setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wt.HANDLE]
setupapi.SetupDiDestroyDeviceInfoList.restype = wt.BOOL

kernel32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p,
                                 wt.DWORD, wt.DWORD, wt.HANDLE]
kernel32.CreateFileW.restype = wt.HANDLE

kernel32.DeviceIoControl.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_void_p,
                                     wt.DWORD, ctypes.c_void_p, wt.DWORD,
                                     ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
kernel32.DeviceIoControl.restype = wt.BOOL

kernel32.WriteFile.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD,
                               ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
kernel32.WriteFile.restype = wt.BOOL

kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.CloseHandle.restype = wt.BOOL


def _enumerate_interface_paths(guid):
    """Every present device-interface path for one interface class GUID."""
    hdev = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if not hdev or hdev == INVALID_HANDLE_VALUE:
        return []
    paths = []
    index = 0
    try:
        while True:
            ifd = SP_DEVICE_INTERFACE_DATA()
            ifd.cbSize = ctypes.sizeof(ifd)
            if not setupapi.SetupDiEnumDeviceInterfaces(
                    hdev, None, ctypes.byref(guid), index, ctypes.byref(ifd)):
                break
            index += 1
            need = wt.DWORD(0)
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                hdev, ctypes.byref(ifd), None, 0, ctypes.byref(need), None)
            if need.value < 4:
                continue
            buf = ctypes.create_string_buffer(need.value)
            # cbSize is 8 on x64 and 6 on x86 (DWORD + one WCHAR, aligned)
            ctypes.c_uint32.from_buffer(buf).value = (
                8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6)
            if not setupapi.SetupDiGetDeviceInterfaceDetailW(
                    hdev, ctypes.byref(ifd), ctypes.byref(buf), need.value,
                    ctypes.byref(need), None):
                continue
            paths.append(ctypes.wstring_at(ctypes.addressof(buf) + 4))
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(hdev)
    return paths


def enumerate_hid_paths():
    """Every HID interface path on the system."""
    guid = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(guid))
    return _enumerate_interface_paths(guid)


def enumerate_keyboard_paths():
    """Every keyboard device-interface path (one per keyboard device)."""
    d1, d2, d3, data4 = KEYBOARD_INTERFACE_GUID
    guid = GUID(d1, d2, d3, (ctypes.c_ubyte * 8)(*data4))
    return _enumerate_interface_paths(guid)


def open_path(path):
    """Open a HID interface read/write, falling back to write-only.

    Windows' keyboard driver keeps the HID keyboard collection open for reading,
    so read+write is refused with ERROR_ACCESS_DENIED. Write-only is accepted and
    is all we need for an LED report.
    """
    last_error = 0
    for access in (GENERIC_READ | GENERIC_WRITE, GENERIC_WRITE):
        handle = kernel32.CreateFileW(
            path, access, FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING, 0, None)
        if handle and handle != INVALID_HANDLE_VALUE:
            return handle, 0
        last_error = ctypes.get_last_error()
    return None, last_error


def close(handle):
    try:
        kernel32.CloseHandle(handle)
    except Exception:
        pass


def attributes(handle):
    attrs = HIDD_ATTRIBUTES()
    attrs.Size = ctypes.sizeof(attrs)
    if hid.HidD_GetAttributes(handle, ctypes.byref(attrs)):
        return attrs
    return None


def product_string(handle):
    buf = ctypes.create_unicode_buffer(256)
    if hid.HidD_GetProductString(handle, ctypes.byref(buf),
                                 ctypes.sizeof(buf)):
        return buf.value
    return ""


def caps(handle):
    preparsed = ctypes.c_void_p()
    if not hid.HidD_GetPreparsedData(handle, ctypes.byref(preparsed)):
        return None
    try:
        out = HIDP_CAPS()
        status = hid.HidP_GetCaps(preparsed, ctypes.byref(out))
        if status != 0x00110000:            # HIDP_STATUS_SUCCESS
            return None
        return out
    finally:
        hid.HidD_FreePreparsedData(preparsed)


def _report_buffers(length, on):
    """Candidate LED report layouts, most likely first."""
    length = int(length or 0)
    if length < 1:
        return []
    led = LED_SCROLLLOCK if on else 0x00
    layouts = []

    if length >= 2:                         # report ID 0 + LED byte
        buf = (ctypes.c_ubyte * length)()
        buf[0] = 0x00
        buf[1] = led
        layouts.append(("id0+led", buf, length))

    if length == 1:                         # LED byte only, no report ID
        buf = (ctypes.c_ubyte * 1)()
        buf[0] = led
        layouts.append(("led-only", buf, 1))

    return layouts


def lock_flags():
    """NumLock/CapsLock bits as Windows currently sees them."""
    flags = 0
    if user32.GetKeyState(VK_NUMLOCK) & 1:
        flags |= KEYBOARD_NUM_LOCK_ON
    if user32.GetKeyState(VK_CAPITAL) & 1:
        flags |= KEYBOARD_CAPS_LOCK_ON
    return flags


class KeyboardDevice:
    """Set indicators on one keyboard through its device-interface handle.

    `IOCTL_KEYBOARD_SET_INDICATORS` is the route Windows itself uses. The handle
    belongs to a single keyboard device, so this can never touch the laptop's
    internal keyboard. Only ScrollLock is changed; NumLock and CapsLock are read
    from the system lock state and kept.

    The CASUE reports `0` for every indicator query even while its LED is on, so
    the ScrollLock state is tracked here instead of trusting the read-back.
    """

    def __init__(self, path):
        self.path = path
        self.handle = None
        self.scroll_on = None
        self.last_write = 0.0
        self.error = ""

    def open(self):
        self.close()
        handle, err = open_path(self.path)
        if not handle:
            self.error = f"CreateFile failed (error {err})"
            return False
        self.handle = handle
        self.scroll_on = None
        self.last_write = 0.0
        self.error = ""
        return True

    def close(self):
        if self.handle:
            close(self.handle)
            self.handle = None

    def query_flags(self):
        if not self.handle:
            return None
        params = (wt.USHORT * 2)()
        returned = wt.DWORD(0)
        size = ctypes.sizeof(params)
        if not kernel32.DeviceIoControl(
                self.handle, IOCTL_KEYBOARD_QUERY_INDICATORS,
                ctypes.byref(params), size, ctypes.byref(params), size,
                ctypes.byref(returned), None):
            return None
        return int(params[1])

    def set_flags(self, flags):
        if not self.handle:
            return False
        params = (wt.USHORT * 2)(0, flags & 0xFFFF)
        returned = wt.DWORD(0)
        if not kernel32.DeviceIoControl(
                self.handle, IOCTL_KEYBOARD_SET_INDICATORS,
                ctypes.byref(params), ctypes.sizeof(params), None, 0,
                ctypes.byref(returned), None):
            self.error = ("IOCTL_KEYBOARD_SET_INDICATORS failed "
                          f"(error {ctypes.get_last_error()})")
            return False
        return True

    def set_scroll(self, on):
        """Set only the ScrollLock indicator; leave Num/Caps as they are.

        Writes when the wanted state changes, and re-asserts once a second in
        case Windows or the Scroll Lock key changed the LED behind our back.
        """
        now = time.monotonic()
        if (self.scroll_on == on and self.last_write
                and now - self.last_write < 1.0):
            return True
        flags = lock_flags() & ~KEYBOARD_SCROLL_LOCK_ON
        if on:
            flags |= KEYBOARD_SCROLL_LOCK_ON
        ok = self.set_flags(flags)
        if ok:
            self.scroll_on = on
            self.last_write = now
            self.error = ""
        return ok

    def describe(self):
        flags = self.query_flags()
        if flags is None:
            return "indicator query failed"
        return f"reported indicators=0x{flags:04X}"


class Backend:
    """Owns the LED handle and keeps the ScrollLock bit where the app wants it."""

    def __init__(self):
        self.keydev = None
        self.handle = None
        self.caps = None
        self.path = ""
        self.method = ""
        self.layout = ""
        self.error = ""
        self.last_sent = None
        self.last_write = 0.0

    # -- connection ---------------------------------------------------------
    def connect(self):
        self.disconnect()

        hid_paths = [p for p in enumerate_hid_paths()
                     if "vid_2a7a" in p.lower() and "pid_959f" in p.lower()]
        kbd_paths = [p for p in enumerate_keyboard_paths()
                     if "vid_2a7a" in p.lower() and "pid_959f" in p.lower()]
        if not hid_paths and not kbd_paths:
            self.error = ("No keyboard interface with VID 2A7A / PID 959F "
                          "found.")
            return False

        # Primary route: the CASUE's own keyboard-interface handle. The
        # indicator IOCTL is handled per keyboard device, so this cannot touch
        # the laptop's internal keyboard.
        kbd_errors = []
        for path in kbd_paths:
            dev = KeyboardDevice(path)
            if not dev.open():
                kbd_errors.append(dev.error)
                continue
            c = caps(dev.handle)
            if not (c and c.UsagePage == 1 and c.Usage == 6):
                kbd_errors.append(f"{path}: not a keyboard collection")
                dev.close()
                continue
            if dev.query_flags() is None:
                kbd_errors.append(f"{path}: indicator query failed")
                dev.close()
                continue
            self.keydev = dev
            self.path = path
            self.method = "KeyboardInterface"
            self.error = ""
            return True

        # Fallback: talk to the HID keyboard collection directly.
        candidates = []
        for path in hid_paths:
            handle, err = open_path(path)
            if not handle:
                candidates.append((path, None, err))
                continue
            attrs = attributes(handle)
            if attrs and (attrs.VendorID != VENDOR_ID
                          or attrs.ProductID != PRODUCT_ID):
                close(handle)
                continue
            candidates.append((path, handle, 0))

        def rank(item):
            handle = item[1]
            c = caps(handle) if handle else None
            is_kbd = bool(c and c.UsagePage == 1 and c.Usage == 6)
            has_out = bool(c and c.OutputReportByteLength > 0)
            return (0 if is_kbd else 1, 0 if has_out else 1, item[0])

        candidates.sort(key=rank)

        errors = []
        chosen = None
        for path, handle, err in candidates:
            if not handle:
                errors.append(f"{path}: open error {err}")
                continue
            if chosen is None:
                chosen = (path, handle)
            else:
                close(handle)           # keep exactly one handle open

        if chosen:
            self.path, self.handle = chosen
            self.caps = caps(self.handle)
            self.method = "HID"
            self.error = ""
            return True

        detail = "; ".join(errors) if errors else "no usable HID collection"
        self.error = (f"Keyboard interface: "
                      f"{'; '.join(kbd_errors) or 'none'}. "
                      f"HID fallback: {detail}.")
        return False

    def disconnect(self):
        if self.keydev:
            self.keydev.close()
        self.keydev = None
        if self.handle:
            close(self.handle)
        self.handle = None
        self.caps = None
        self.path = ""
        self.method = ""
        self.layout = ""
        self.last_sent = None

    @property
    def connected(self):
        return self.keydev is not None or self.handle is not None

    # -- LED writes ---------------------------------------------------------
    def _send(self, on):
        length = self.caps.OutputReportByteLength if self.caps else 0
        if length < 1:
            self.error = "HID interface exposes no output report"
            return "", "", None

        attempts = []
        for name, buf, size in _report_buffers(length, on):
            if hid.HidD_SetOutputReport(self.handle, ctypes.byref(buf), size):
                return "HidD_SetOutputReport", name, 0
            attempts.append(("HidD_SetOutputReport", name,
                             ctypes.get_last_error()))

            written = wt.DWORD(0)
            if kernel32.WriteFile(self.handle, ctypes.byref(buf), size,
                                  ctypes.byref(written), None):
                return "WriteFile", name, 0
            attempts.append(("WriteFile", name, ctypes.get_last_error()))

        if not attempts:
            self.error = "No LED report layout available"
            return "", "", None
        self.error = "; ".join(f"{m}({n}) err={e}" for m, n, e in attempts)
        return "", "", attempts[-1][2]

    def set_led(self, on, force=False):
        """Set the strip. Returns True if the driver accepted the change."""
        if self.keydev:
            ok = self.keydev.set_scroll(on)
            if ok:
                self.method = "KeyboardInterface"
                self.last_sent = on
                self.last_write = time.monotonic()
            else:
                self.error = self.keydev.error
            return ok

        if not self.handle:
            return False
        now = time.monotonic()
        if not force and self.last_sent == on and now - self.last_write < 1.0:
            return True
        method, layout, err = self._send(on)
        if method:
            self.method, self.layout = method, layout
            self.last_sent = on
            self.last_write = now
            return True
        if err is not None:
            self.error = f"LED report rejected (error {err})"
        return False

    # -- diagnostics --------------------------------------------------------
    def diagnose(self):
        lines = [f"Windows keyboard report for CASUE USB KB "
                 f"({VENDOR_ID:04X}:{PRODUCT_ID:04X})", ""]

        lines.append("Keyboard interfaces (primary path)")
        kbd_paths = enumerate_keyboard_paths()
        casue = [p for p in kbd_paths
                 if "vid_2a7a" in p.lower() and "pid_959f" in p.lower()]
        if not casue:
            lines.append("  no CASUE keyboard interface found")
        for path in casue:
            dev = KeyboardDevice(path)
            if not dev.open():
                lines.append(f"  {path}")
                lines.append(f"    open FAILED: {dev.error}")
                continue
            try:
                c = caps(dev.handle)
                usage = (f"page {c.UsagePage} id {c.Usage}" if c else "none")
                lines.append(f"  {path}")
                lines.append(f"    usage: {usage}; {dev.describe()}")
                for on in (False, True):
                    ok = dev.set_scroll(on)
                    lines.append(
                        f"    ScrollLock {'on ' if on else 'off'} -> "
                        f"{'accepted' if ok else 'FAILED'}"
                        f"{'' if ok else f' ({dev.error})'}")
                    time.sleep(0.25)
                lines.append("    reached this board's LED (left ScrollLock on)")
            finally:
                dev.close()

        others = [p for p in kbd_paths if p not in casue]
        lines.append(f"  other keyboards present: {len(others)} "
                     f"(left untouched)")

        paths = enumerate_hid_paths()
        lines += ["", f"HID interfaces found: {len(paths)}"]
        for path in paths:
            if "vid_2a7a" not in path.lower() or "pid_959f" not in path.lower():
                continue
            lines.append(f"\n  path: {path}")
            handle, err = open_path(path)
            if not handle:
                lines.append(f"  open: FAILED (error {err})")
                if err == 5:
                    lines.append("  -> access denied: run as administrator")
                continue
            try:
                attrs = attributes(handle)
                if attrs:
                    lines.append(f"  ids: {attrs.VendorID:04X}:{attrs.ProductID:04X} "
                                 f"v{attrs.VersionNumber:04X}")
                lines.append(f"  product: {product_string(handle)!r}")
                c = caps(handle)
                if c:
                    lines.append(f"  usage: page {c.UsagePage} id {c.Usage}")
                    lines.append(f"  report bytes: in {c.InputReportByteLength}, "
                                 f"out {c.OutputReportByteLength}, "
                                 f"feature {c.FeatureReportByteLength}")
                for on in (False, True):
                    if not c or c.OutputReportByteLength < 1:
                        lines.append("  LED: skipped (collection has no output "
                                     "report)")
                        break
                    method, layout, e = self._send_any(handle, c, on)
                    lines.append(f"  LED {'on ' if on else 'off'} -> "
                                 f"{method or 'FAILED'} {layout or ''} "
                                 f"{'' if method else f'err={e}'}")
                    time.sleep(0.2)
            finally:
                close(handle)
        lines += ["", "If a keyboard interface row says 'accepted', the light "
                      "is being driven through Windows' own LED path.",
                  "The HID rows are fallback information only. Error 1 "
                  "(ERROR_INVALID_FUNCTION) is expected on this board's "
                  "keyboard collection: it advertises a 2-byte output report "
                  "but the driver rejects it."]
        return "\n".join(lines)

    def _send_any(self, handle, c, on):
        length = c.OutputReportByteLength if c else 0
        if length < 1:
            return "", "", None
        err = 0
        for name, buf, size in _report_buffers(length, on):
            if hid.HidD_SetOutputReport(handle, ctypes.byref(buf), size):
                return "HidD_SetOutputReport", name, 0
            written = wt.DWORD(0)
            if kernel32.WriteFile(handle, ctypes.byref(buf), size,
                                  ctypes.byref(written), None):
                return "WriteFile", name, 0
            err = ctypes.get_last_error()
        return "", "", err
