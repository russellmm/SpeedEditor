# SpeedEditor key map

USB device `1edb:da0e`; 43 buttons. All assignments below are editable. STOP/PLAY,
CAM1 and JOG were verified in Linux captures. Windows native capture additionally
confirmed SHTL (`0x1c`), JOG (`0x1d`) and SCRL (`0x1e`) on October 28, 2026.
The subsequent GUI adapter test confirmed CAM9 (`0x3b`) with its Space override
while the wheel stayed native. The remaining 37 button IDs use the published
protocol and have not been verified physically. See
[native wheel observations](docs/NATIVE_WHEEL.md).

**The legacy Resolve shortcut preset is an unverified desktop approximation.**
Windows also offers the experimental **Resolve native wheel** profile: every
button starts Native, with explicit Shortcut or Disabled overrides saved
separately. JOG, SCRL and SHTL always stay native in that mode. The table below
lists desktop/starter shortcuts, not native-wheel overrides. Choose **Use native
Resolve** to detach all mapping. See [adapter setup](docs/RESOLVE_ADAPTER.md).

| Hardware ID | Button label | Desktop shortcut | Resolve starter shortcut |
| --- | --- | --- | --- |
| `0x01` | SMART INSRT | Ctrl+N | F9 |
| `0x02` | APPND | Ctrl+Shift+N | Shift+F12 |
| `0x03` | RIPL OWR | Ctrl+S | Shift+F10 |
| `0x04` | CLOSE UP | Ctrl+Plus | — |
| `0x05` | PLACE ON TOP | Alt+Tab | F12 |
| `0x06` | SRC OWR | Ctrl+O | — |
| `0x07` | IN | Home | I |
| `0x08` | OUT | End | O |
| `0x09` | TRIM IN | PageUp | — |
| `0x0A` | TRIM OUT | PageDown | — |
| `0x0B` | ROLL | Tab | — |
| `0x0C` | SLIP SRC | Shift+Tab | — |
| `0x0D` | SLIP DEST | Ctrl+Tab | — |
| `0x0E` | TRANS DUR | Ctrl+Shift+Tab | — |
| `0x0F` | CUT | Ctrl+X | Ctrl+B |
| `0x10` | DIS | Ctrl+C | Ctrl+T |
| `0x11` | SMTH CUT | Ctrl+V | — |
| `0x1A` | SOURCE | Alt+Left | Q |
| `0x1B` | TIMELINE | Alt+Right | Q |
| `0x1C` | SHTL | — | — |
| `0x1D` | JOG | — | — |
| `0x1E` | SCRL | — | — |
| `0x1F` | SYNC BIN | Ctrl+F | — |
| `0x22` | TRANS | Ctrl+T | — |
| `0x25` | VIDEO ONLY | PreviousSong | — |
| `0x26` | AUDIO ONLY | NextSong | — |
| `0x2B` | RIPL DEL | Delete | — |
| `0x2C` | AUDIO LEVEL | Mute | — |
| `0x2D` | FULL VIEW | F11 | Ctrl+F |
| `0x2E` | SNAP | Super+E | N |
| `0x2F` | SPLIT | Ctrl+Shift+T | — |
| `0x30` | LIVE OWR | Ctrl+Z | Ctrl+Z |
| `0x31` | ESC | Esc | Esc |
| `0x33` | CAM1 | Ctrl+1 | 1 |
| `0x34` | CAM2 | Ctrl+2 | 2 |
| `0x35` | CAM3 | Ctrl+3 | 3 |
| `0x36` | CAM4 | Ctrl+4 | 4 |
| `0x37` | CAM5 | Ctrl+5 | 5 |
| `0x38` | CAM6 | Ctrl+6 | 6 |
| `0x39` | CAM7 | Ctrl+7 | 7 |
| `0x3A` | CAM8 | Ctrl+8 | 8 |
| `0x3B` | CAM9 | Ctrl+9 | 9 |
| `0x3C` | STOP PLAY | Space | Space |

## Wheel maps

Both built-in profiles now use **Standard** transport by default. Select
**Custom** for an individual wheel mode to program its left/right actions.
Imported profiles without a behavior field keep their assigned shortcuts.
An experimental **Measured** option uses the captured input scales and SHTL
samples, with separate output settings; see [measured transport](docs/MEASURED_TRANSPORT.md).

| Mode | Standard behavior in either profile | Threshold |
| --- | --- | --- |
| JOG | Pause, then step one frame backward / forward | 360 |
| SCRL | Pause, then step ten frames backward / forward | 360 |
| SHTL | Latched reverse / forward playback levels | 2160 |

In Standard mode, JOG and SCRL emit K and arrow keys only in response to movement. SHTL uses
relative displacement from its entry point to select four speed levels, sending
K and J/L taps when the level changes. Returning to neutral, STOP/PLAY, a mode
change, or stopping the mapper stops a latched shuttle. Actual speed multipliers
depend on the focused editor. This emulation does not provide native Fairlight
or Cut-page features, and has not been tested inside a video editor.

The Resolve profile uses keyboard approximations. CAM buttons currently send
digits; verify their behavior in your installed Resolve keyboard preset.
See [README](README.md) for the native Resolve limitation and setup.

Protocol reference: [Sylvain Munaut’s driver](https://github.com/smunaut/blackmagic-misc). Shortcut reference: [Blackmagic Design Editor’s Guide](https://documents.blackmagicdesign.com/UserManuals/DaVinci-Resolve-20-Editors-Guide.pdf).
