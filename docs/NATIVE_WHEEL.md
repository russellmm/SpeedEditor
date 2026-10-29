# Native Windows wheel observations — October 28, 2026

Context: Windows 11, USB Speed Editor, DaVinci Resolve **Cut page, Source Tape
active**. The user operated the wheel. The mapper stayed disconnected.

REA 6.5.0 attached Frida to the existing Resolve.exe process. The tracing script
`tools/trace_resolve_hid.js` identified the controller by HID vendor/product
1edb:da0e, then observed its HID API calls and completed asynchronous reads. It
did not modify reports or issue controller output commands. Tracing was detached
after capture; Resolve remained responsive.

## Observed configuration

| Physical mode | Button ID | Successful host wheel report | LED report | Input hardware mode |
| --- | --- | --- | --- | --- |
| JOG | `0x1d` | `03 02 00 00 00 00 ff` | `04 01` | 2 |
| SCRL | `0x1e` | `03 02 00 00 00 00 ff` | `04 04` | 2 |
| SHTL | `0x1c` | `03 03 00 00 00 00 ff` | `04 02` | 3 |

Input wheel reports were 13 bytes on Windows: the seven protocol bytes followed
by six zero padding bytes. The signed value is little-endian at bytes 2–5;
byte 1 identifies the hardware wheel mode. The parser now accepts zero padding.

JOG and SCRL used the same relative hardware mode and comparable full-turn raw
totals. It is an **inference** that their differing navigation behavior is
implemented inside Resolve rather than selected by a different encoder report
mode. Native context-specific gains were not measured.

SHTL used hardware mode 3, identified in the published protocol as absolute with
a zero dead band. The captured values include zero and small positive/negative
positions. The user reported **0.25× forward continued with the wheel completely
stationary**. A subsequent session sampled forward and reverse rates through
64× and tested SHTL stop/neutral behavior; see [SHUTTLE_CURVE.md](SHUTTLE_CURVE.md).
API observation times are not precise timestamps of the user's speed-display
observation. The samples do not establish exact speed transition thresholds.

## User-marked rotation trials

| Trial | Trace interval, milliseconds | Wheel reports | Signed raw total |
| --- | --- | --- | --- |
| JOG, one clockwise turn | after 201133 through 268654 | 480 | +1,474,715 |
| JOG, one counterclockwise turn | after 268654 through 321440 | 518 | −1,466,767 |
| SCRL, clockwise turn with reverse correction | after 321440 through 373128 | 532 | +1,468,558 |

The user clarified the SCRL trial was intended as 360°, with a slight overshoot
and reverse correction. Its positive and negative contributions were +1,521,118
and −52,560. The JOG magnitudes differ by about 0.54%; these hand-rotated trials
are approximate calibration, not precision angular metrology. Roughly 1.47
million relative units per turn was observed in mode 2. Standard and Custom
desktop modes still program mode 0; this capture does not prove an identical
angular scale in mode 0. The optional [Measured desktop mode](MEASURED_TRANSPORT.md)
programs mode 2 for JOG/SCRL and uses these approximate per-turn calibrations.
Existing default sensitivity settings were preserved.

## Evidence and reproduction

The ignored `artifacts/rea-native-resolve.json` contains seven authenticated REA
Evidence records with the complete captured message snapshots. No snapshot
reported truncation. Supporting records include:

- Setup and selected device: `ev_b3b79b9a31fb6f8d3aa2d3e32e1dbfd5ce0c7f8c205976bd4a6dc17d78872367`.
- JOG clockwise endpoint: `ev_d828cc320cba469eb6388895e30a22c3207002ed2bf0fef28280bb8f4b918ce2`.
- JOG reverse endpoint: `ev_5a386a6041cb31c227db0adf3b24aa6193609550a6bffa25865d1d00a1dc40f0`.
- SCRL and final snapshot: `ev_7e538486863c5f570bf626de0ea0e0323a38be8377cfa69c1bf7774834880bb5`.

Summarize the saved bundle without attaching to Resolve:

```powershell
.\.venv-win\Scripts\python.exe tools/analyze_native_hid.py artifacts/rea-native-resolve.json --output artifacts/native-summary.json
.\.venv-win\Scripts\python.exe tools/analyze_native_hid.py artifacts/rea-native-resolve.json --start-ms 201133 --end-ms 268654
```

The summary retains evidence IDs, the bundle SHA-256, hardware mode labels,
padding lengths and truncation status. Cumulative status snapshots are
deduplicated. Sum only relative mode 0/2 values, never absolute mode 3 positions.

Unmeasured: timeline/Source Tape frame displacement per revolution, exact speed
thresholds, continuous shuttle response, Edit/Fairlight/other Cut contexts, mode-0 angular
scale, and standalone Windows mapper output. The desktop keyboard wheel and
the separate [Resolve native-wheel adapter](RESOLVE_ADAPTER.md) use different
control paths. The Standard desktop four-level keyboard shuttle does
not reproduce native 0.25× playback or context-sensitive Resolve operations.
