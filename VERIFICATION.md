# Hardware verification — October 26, 2026

- USB unit: Blackmagic Design DaVinci Resolve Speed Editor, 1edb:da0e.
- Linux hidraw authentication: successful.
- Device access setup: installed and confirmed for the local user.
- Virtual keyboard/scroll device: created and closed successfully; no test keys sent.
- Live button IDs: STOP_PLAY = 0x3c; CAM1 = 0x33; JOG = 0x1d.
- Live button release reports: confirmed.
- Wheel: both positive and negative deltas; multiples of 360.
- Battery: 2%, charging.
- Automatic battery query with mappings stopped: verified at 4%, Charging.
- Live wheel reports captured: 218.
- Original shortcut-profile thresholds during the live test: JOG 720, SCRL 3600, SHTL 2160.
- New Standard transport defaults: JOG and SCRL 360; SHTL 2160. Per-mode Custom overrides remain available.
- Automated checks: 37 unit tests plus GUI smoke at normal and high DPI passed.
- Transport tests cover frame stepping, faster search, latched shuttle levels, neutral/reverse, stopping on mode changes and disconnects, and legacy/custom profile preservation.
- New keyboard transport defaults have not been verified inside a video editor.
- Untested: remaining 40 physical buttons; delivery into target applications; native Resolve.
- Not implemented: custom remapping while native Resolve owns the controller.

# Windows and native wheel verification — October 28, 2026

- Windows 11 port implements HIDAPI access, busy-interface discovery, SendInput
  output, Resolve.exe detection, launch scripts and DPI-aware Tk UI.
- Windows unit suite: 49 run, 48 passed, one Linux-specific test skipped.
- Ubuntu WSL suite: 49 run, 43 passed, six Windows-specific tests skipped.
- GUI smoke checks: normal/high DPI passed on both platforms. Subsequent Windows
  checks use `--headless`; Linux screenshot rendering uses Xvfb. Pillow replaces
  the previous ImageMagick screenshot dependency.
- Resolve retained the controller throughout native tests. Tracing is detached.
- Cut page / Source Tape active: native JOG and SCRL configure hardware mode 2;
  SHTL configures mode 3. Incoming wheel buffers have 13 bytes with zero padding.
- JOG user-marked turns: +1,474,715 clockwise and −1,466,767 counterclockwise.
- SCRL clockwise turn including overshoot correction: net +1,468,558.
- The user confirmed stationary-wheel SHTL playback continued at 0.25× forward.
- Further SHTL samples cover forward/reverse 0.25× through 64×, including held
  endpoints +4096/−4096. Rates are manually reported plateau samples, not exact
  transition thresholds; some intermediate reverse rates remain unsampled.
- Re-pressing an already-selected SHTL stops playback while retaining neutral;
  the user confirmed switching through JOG/SCRL and returning to SHTL sets a new
  neutral. See [sampled shuttle curve and origin behavior](docs/SHUTTLE_CURVE.md).
- Captured a native battery input report of 100%, not charging; this does not
  verify the app's own standalone Windows battery query.
- Keyboard/scroll output was mocked; no mapped shortcuts were sent to the desktop.
- Remaining: standalone Windows authentication, battery and shortcut delivery
  with Resolve stopped; precise speed thresholds and frame-displacement measurements;
  remaining 38 physical buttons; custom mappings inside native Resolve.

See [native evidence and limitations](docs/NATIVE_WHEEL.md) and
[Windows port status](docs/WINDOWS_PORT.md).

# Experimental Resolve adapter — October 28, 2026

- Added the Resolve native wheel control mode, per-button Native / Shortcut /
  Disabled settings, a separate `resolve_buttons` profile field, and an all-native
  starter profile. Desktop settings and legacy profiles are preserved.
- Production monitor attached to Resolve 21.1.0.14, received 240 wheel updates
  and eight key reports, then detached. The user confirmed normal native JOG,
  SCRL and SHTL behavior while it was connected.
- Actual Windows Frida runtime loaded the production script with real-device
  mapping disabled; synthetic reports verified button replacement, reserved JOG
  pass-through and unchanged wheel bytes. No shortcut output was enabled.
- Current Windows suite: 61 tests, 60 passed and one Linux-only test skipped.
- Current Ubuntu WSL suite: 61 tests, 53 passed and eight Windows/Node tests skipped.
- Hidden Windows and rendered Xvfb GUI checks pass at normal/high DPI, including
  separate native-button editing, protected wheel modes and auto-selected profile.
- User-started GUI live check passed: CAM9 → Space toggled play/pause while JOG,
  SCRL and SHTL continued natively. The ignored test profile is
  `artifacts/resolve-native-live-check.json`. Other remaps/pages remain unverified.
- Native wheel control is preserved by passing its reports to Resolve; the
  sampled speed curve is not used to emulate native transport in this mode.

See [Resolve adapter setup and limits](docs/RESOLVE_ADAPTER.md).

# Shortcut punctuation and recording — October 29, 2026

- Literal `Ctrl+,` and `Ctrl + ,` now resolve to the same key codes as
  `Ctrl+Comma`. Common unshifted punctuation and friendly key names are accepted;
  existing `Plus` profiles retain their meaning.
- Added a focused shortcut recorder with preview, Use shortcut and Cancel.
  Recording edits the field; Apply & save remains necessary to update a profile.
  Native / Disabled buttons and native wheel mode buttons cannot be recorded.
- Windows suite: 69 tests, 68 passed and one Linux-specific test skipped.
- Ubuntu WSL suite: 69 tests, 61 passed and eight Windows/Node tests skipped.
- Normal/high-DPI GUI checks passed with hidden Windows windows and Xvfb on
  Linux. Xvfb key events exercised the recorder binding with Ctrl+Comma; rendered
  layouts were inspected. Tests cover acceptance, cancellation, profile saving,
  punctuation aliases, shifted keys and platform modifier flags.
- This change has not yet had a physical-keyboard recording or Ctrl+Comma
  delivery check in the user's live Resolve session.

# Optional measured desktop transport — October 29, 2026

- Added opt-in Measured behavior per wheel mode; Standard defaults and legacy
  Custom profiles remain unchanged. Native Resolve's pass-through is unaffected.
- JOG/SCRL select the captured relative hardware mode 2 and use the retained
  rotation calibration with user-selected steps per turn. SHTL selects absolute
  mode 3 and estimates signed rates from the portable ledger, including retained
  neutral on repeated SHTL presses and recentering only on mode re-entry.
- Sample selection uses median positions and nearest-sample boundaries. These
  are estimates, not measured speed thresholds; missing reverse rates are not
  mirrored. Per-speed shortcuts or explicitly approximate J/K/L output are available.
- Windows suite: 83 tests, 82 passed and one Linux-only test skipped.
- Ubuntu WSL suite: 83 tests, 75 passed and eight Windows/Node tests skipped.
- Hidden Windows GUI behavior and normal/high-DPI Xvfb rendering checks passed.
  The settings dialog, nested shortcut recorder, Assign/Save/Cancel, inactive
  native-mode controls and target-versus-output log were exercised.
- Tests use synthetic HID reports and mocked output, including all retained
  speed samples, absolute position handling, mode transitions, stale-report
  filtering, profile updates, bounded output and monitor-only operation.
- Standalone mode-2/mode-3 hardware operation and target-editor playback still
  need a live check with Resolve stopped. The current Resolve session was not
  interrupted or switched to desktop mapping.

See [measured transport setup and limits](docs/MEASURED_TRANSPORT.md).
