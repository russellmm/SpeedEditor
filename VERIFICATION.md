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
