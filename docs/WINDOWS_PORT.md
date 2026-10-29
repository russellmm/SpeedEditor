# Windows 11 port

The implementation now includes Windows HIDAPI transport, discovery of busy USB
HID interfaces, SendInput keyboard/scroll output, Resolve.exe detection, DPI-aware
Tk windows, scrollable editor controls, and PowerShell/double-click launchers.
The Linux backend and existing profile format are preserved. The app starts
disconnected and sends shortcuts only after the user starts mapping.

Run `setup.ps1` once, then `run.ps1` or double-click `SpeedEditor.cmd`.
Python 3.13 and `.venv-win` were used on the tested machine. See README.md for
installation and `requirements-dev.txt` for development dependencies.

## Verified on October 28, 2026

- Windows sees the USB Speed Editor and correctly identifies Resolve.exe.
- A busy controller remains visible in the editor and diagnostics rather than
  being incorrectly reported as disconnected.
- Resolve has exclusive HID access on this setup. Desktop mapping refuses to
  open the controller while Resolve runs; battery queries are also deferred.
  The experimental native-wheel adapter instead uses Resolve's own HID read path.
- All 61 unit tests run: Windows passes 60 and skips the Linux output test;
  Ubuntu WSL passes 53 and skips eight tests requiring Windows or Node.js.
- GUI smoke checks pass at normal and high DPI on Windows and Linux. Windows
  screenshots were inspected; subsequent Windows behavior checks run with a
  hidden window. Linux rendering uses Xvfb.
- Native input and host configuration reports were captured with REA/Frida in
  Resolve's Cut page with Source Tape active. See NATIVE_WHEEL.md.
- No mapped keyboard/scroll events were sent. Output tests mock SendInput.
- The production Resolve adapter attached in Monitor only and received 240
  native wheel updates and eight key reports; the user confirmed normal JOG,
  SCRL and SHTL behavior. Frida runtime checks exercised synthetic button
  replacement with real-device mapping disabled. See RESOLVE_ADAPTER.md.
- The user then opened the GUI live-check profile, started mapping, and confirmed
  CAM9 → Space play/pause together with normal native JOG/SCRL/SHTL operation.

## Remaining hardware checks

On October 29, v0.1.0 authenticated the attached controller, configured Standard
desktop wheel mode and LEDs, connected in Monitor only for three seconds, and
stopped cleanly with Resolve closed. No keyboard output was created. This fixes
an incorrect write-length check: the 2-byte LED command successfully returns a
7-byte padded write count on Windows HIDAPI. Its
[Windows implementation](https://github.com/libusb/hidapi/blob/hidapi-0.14.0/windows/hid.c#L929-L993)
pads short output reports to the collection's maximum output size.

Automatic battery queries without Resolve, live desktop button/wheel monitoring,
measured mode-2/mode-3 operation, desktop mapping and end-to-end SendInput delivery
still need further live checks. The combined Resolve adapter is live-verified for
CAM9 → Space; other button/shortcut combinations and Resolve contexts need more
testing. Desktop Standard wheel shortcuts remain keyboard approximations.

The optional Raw Input recorder could register the controller before the app
restart, but received no physical test sequence in that window. After restart,
Resolve's collection was absent from Raw Input. Use the saved REA evidence for
the successful measurements; do not interpret either Raw Input attempt as a
wheel calibration.
