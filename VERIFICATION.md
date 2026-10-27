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
- Desktop thresholds: JOG 720, SCRL 3600, SHTL 2160.
- Automated checks: 25 unit tests plus GUI smoke at normal and high DPI passed.
- Untested: remaining 40 physical buttons; delivery into target applications; native Resolve.
- Not implemented: custom remapping while native Resolve owns the controller.
