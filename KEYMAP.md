# SpeedEditor key map

USB device `1edb:da0e`; 43 buttons. All assignments below are editable. Defaults are editable. STOP/PLAY, CAM1 and JOG were verified by live button captures; the other 40 buttons use the published protocol IDs.

**Resolve shortcut preset is unverified and inactive while native Resolve is running.** Choose “Use native Resolve” for normal Resolve operation. Native button labels describe native controls; ordinary shortcuts cannot reproduce every operation. Blank entries send nothing.

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
| `0x3C` | STOP PLAY | PlayPause | Space |

## Wheel maps

All three maps use relative motion. SHTL is a selectable map, not native absolute shuttle. Left/right orientation and sensitivity need confirmation using the physical wheel.

| Mode | Desktop left / right | Threshold | Resolve left / right | Threshold |
| --- | --- | --- | --- | --- |
| JOG | ScrollUp / ScrollDown | 720 | Left / Right | 360 |
| SCRL | PageUp / PageDown | 3600 | Up / Down | 3600 |
| SHTL | VolumeDown / VolumeUp | 2160 | J / L | 3600 |

The Resolve profile uses keyboard approximations. CAM buttons currently send digits; verify their behavior in your installed Resolve keyboard preset. J/L wheel output taps playback commands; use STOP/PLAY to stop. See [README](README.md) for the native Resolve limitation and setup.

Protocol reference: [Sylvain Munaut’s driver](https://github.com/smunaut/blackmagic-misc). Shortcut reference: [Blackmagic Design Editor’s Guide](https://documents.blackmagicdesign.com/UserManuals/DaVinci-Resolve-20-Editors-Guide.pdf).
