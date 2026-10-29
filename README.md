# SpeedEditor

Current version: **0.1.0**, displayed beside the app name and in the window title.
You can also run `python -m speededitor --version`. Compare this number with the
README on GitHub when checking which version you have open.

Use the **Blackmagic Design DaVinci Resolve Speed Editor** as a configurable USB
controller on **Windows 11**. Map buttons to keyboard shortcuts while **DaVinci
Resolve continues to control the wheel natively**, or use the separate desktop
mapper with other applications.

The Windows Resolve adapter is **experimental**, with a successful live test on
Resolve **21.1.0.14**: CAM9 was mapped to play/pause while JOG, SCRL and SHTL
continued to work natively. It uses a temporary runtime adapter rather than an
official Blackmagic plugin, and compatibility may change with Resolve updates.

The program starts **disconnected, with shortcut output off**. You choose when
to monitor the device or start mapping.

## What it does

- **Resolve native wheel mode:** keep native JOG, SCRL and SHTL behavior, including
  Resolve's playback speeds, neutral position and page-specific wheel operations.
- **Custom Resolve buttons:** set each of the other 40 buttons to **Native**,
  **Shortcut**, or **Disabled**. A shortcut replaces that button's native action.
- **Desktop mode:** assign all 43 buttons and configure Standard, Custom or
  experimental Measured wheel actions for applications outside Resolve.
- **Profiles:** edit and save JSON profiles, make copies, and retain older custom
  mappings. Desktop settings and Resolve button overrides are stored separately.
- **Monitor only:** inspect controls without replacing their native actions or
  sending shortcuts.
- **Battery status:** show percentage and charging state when the interface is
  available. Windows battery queries pause while Resolve owns the controller.

Connect the Speed Editor **by USB**. Bluetooth is not implemented in this app.

## Platform status

| Feature | Windows 11 | Linux |
| --- | --- | --- |
| GUI and profile editing | Implemented; tested | Retained; automated GUI checks pass under WSL/Xvfb |
| Standalone USB desktop mapper | Implemented; end-to-end Windows desktop delivery still needs testing | Existing hidraw/uinput backend; previously tested with USB on Wayland |
| Custom buttons together with Resolve's native wheel | **Experimental; live-tested** | **Not implemented** |
| Fully native Resolve without custom overrides | Detach the adapter and let Resolve operate normally | Release the mapper and let Resolve operate normally |

**Windows 11 is the current platform for the combined native-wheel/custom-button
feature.** The Linux desktop code has been preserved. A Linux version of the
combined mode is a reasonable future port, but needs its own Resolve process/HID
adapter, focus handling and live USB tests. Windows API hooks cannot be reused
unchanged on Linux; passing the shared tests under WSL does not verify native
Resolve integration on a Linux machine. macOS is not supported.

## Windows installation

You need:

- Windows 11 and **Python 3.13**, including tkinter and the Python launcher.
- Git to clone this repository, or an extracted download of the repository.
- A USB-connected Speed Editor. Keep the normal Resolve/Blackmagic device setup;
  this project does not require replacing its USB driver.
- A running DaVinci Resolve instance for native-wheel button mapping.

In PowerShell:

```powershell
git clone https://github.com/russellmm/SpeedEditor.git
cd SpeedEditor
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
.\SpeedEditor.cmd
```

Setup creates **`.venv-win`** and installs the Python dependencies, including
HIDAPI and Frida. The execution-policy option applies only to that PowerShell
process. It does not change your machine's permanent policy.

After setup, double-click **SpeedEditor.cmd** to launch the GUI. No administrator
session is normally needed. Setup defaults to Python 3.13; to select another
installed version, pass `-PythonVersion 3.12` to `setup.ps1`.

To update an existing checkout, stop the adapter, close SpeedEditor, run
`git pull`, then run setup again before reopening the app. Your saved profile
files should be backed up before updating if you edited the built-in examples.

## Use custom buttons with the native Resolve wheel

1. Connect the Speed Editor by USB and open Resolve.
2. Open SpeedEditor and select the **Resolve native wheel** profile. This selects
   **Resolve native wheel (experimental)** as the control mode.
3. Select a button in **Button Assignments**.
4. Choose its behavior:

   | Behavior | Result |
   | --- | --- |
   | **Native** | Resolve receives the button normally. This is the default. |
   | **Shortcut** | Replace the native button action with the keyboard/scroll shortcut you enter. |
   | **Disabled** | Suppress the button without sending a shortcut. |

5. Choose **Apply & save**. For a first check, assign **CAM9 → Space** for
   play/pause, or use a shortcut you already know works in your Resolve layout.
6. Choose **Start mapping**.
7. Return focus to Resolve and move the wheel briefly to arm the input path.
8. Use your mapped buttons while Resolve continues handling the wheel.

**JOG, SCRL and SHTL always remain native** in this mode. Wheel shortcut and
sensitivity fields are disabled because Resolve controls the wheel directly.
The measured shuttle curve is reference data; the adapter does not approximate
it using keyboard commands.

Custom shortcuts apply only while Resolve has focus. They tap once per button
press. Actions such as `Space`, `Ctrl+C`, `Ctrl+Shift+S`, `Alt+Left`, and
`ScrollDown` depend on the target application's shortcut layout.

Choose **Monitor only** to connect without enabling overrides. Choose **Stop
adapter** or **Use native Resolve** to detach and restore fully native buttons.
Those controls stop the adapter; playback itself is controlled by Resolve.

### What stays native

Resolve retains device ownership, authentication, wheel modes, LEDs, playback
speed response and the wheel's context within the current Resolve page.

On the tested **Cut page with Source Tape active**, pressing SHTL while it is
already selected stops playback and retains the existing neutral. Switching to
JOG/SCRL and returning to SHTL establishes a new neutral at the current wheel
position. Sampled native shuttle rates reached **0.25× through 64× in both
directions**. These observations are specific to the tested context, and the
samples are not exact speed-transition thresholds.

See the [adapter details](docs/RESOLVE_ADAPTER.md),
[native wheel observations](docs/NATIVE_WHEEL.md), and
[sampled SHTL curve](docs/SHUTTLE_CURVE.md).

## Use it as a desktop shortcut controller

Close Resolve and select **Desktop shortcuts** as the control mode. Choose the
**Desktop** profile, select a button, enter a shortcut, then choose **Apply &
save**. Leave its assignment blank to send nothing.

Use **Monitor only** first to inspect the controls. Choose **Start mapping** to
send shortcuts to the focused application, and **Stop** to release the device.
The standalone mapper refuses to take the controller while Resolve is running.

Desktop wheel modes default to **Standard** keyboard transport:

| Mode | Standard keyboard behavior | Default threshold |
| --- | --- | --- |
| JOG | Pause, then step one frame backward/forward per movement unit | 360 |
| SCRL | Pause, then step ten frames backward/forward per movement unit | 360 |
| SHTL | Latched reverse/forward J/K/L playback levels | 2160 |

This requires a focused editor with compatible J/K/L and arrow-key bindings.
It is **keyboard emulation**, not exact native Resolve, Cut or Fairlight control.
The Standard desktop shuttle has four playback levels; repeated SHTL stops and recenters
that emulation. Its behavior differs from the native wheel described above.

Select **Custom** for an individual wheel mode to program left/right shortcuts.
Lower thresholds increase sensitivity. Older profiles without a behavior field
retain their existing custom wheel behavior.

### Optional measured desktop transport

Select **Measured** for JOG, SCRL or SHTL, open **Measured transport settings…**,
then **Save settings**. This is experimental and stays off in the starter profiles.
You can mix Measured, Standard and Custom modes in one profile.

- **JOG / SCRL:** use the measured mode-2 rotation scale with adjustable
  **steps per turn**, sending the mode's left/right shortcuts. Defaults of 60
  and 600 steps per turn are starting gains, not measured native frame counts.
- **SHTL:** use absolute mode-3 positions and the captured forward/reverse speed
  samples. Re-pressing SHTL stops while retaining neutral; switching through
  JOG/SCRL and returning establishes a new neutral.
- **Approximate J/K/L:** convert estimated target speeds to J/L tap levels with
  nominal 1/2/4/8/16/32/64× rates. Fractional and odd rates round to a level;
  the target editor determines actual playback speed. The live log distinguishes
  measured targets from approximate output.

Continuous fractional-speed playback is required only in Resolve and remains
handled by its native wheel integration. The desktop settings cover measured
wheel response, steps per turn and Stop; no per-speed shortcut setup is needed.

The curve uses nearest sampled positions; exact transition boundaries were not
measured, and missing reverse rates are not copied from forward samples. It
does **not** recreate exact native Resolve transport through keyboard commands.
Resolve must remain closed for desktop USB ownership. While using Resolve,
choose **Resolve native wheel** to retain its actual native behavior.

Start with **Monitor only** to inspect targets without sending shortcuts. See
[measured transport settings and limitations](docs/MEASURED_TRANSPORT.md).

## Profiles and shortcuts

- **Desktop:** general editing, navigation, browser and media shortcuts.
- **Resolve shortcuts:** a legacy, unverified desktop keyboard preset. CAM1–9
  use plain digits; they are not verified multicam commands.
- **Resolve native wheel:** the Windows adapter profile. Every button starts
  Native; add only the overrides you want.

Use **Save as…** to create a personal copy and **Open…** to load it later.
Personal JSON profiles saved in `profiles/` are ignored by Git; the three
built-in starter profiles remain versioned.
Native-wheel overrides use the optional `resolve_buttons` field: omitted entries
mean Native, a shortcut string means Shortcut, and an empty string means Disabled.
They do not overwrite the profile's desktop button or wheel settings.

Type a shortcut such as **`Ctrl+,`**, **`Ctrl + ,`** or **`Ctrl+Comma`**; all three
mean the same thing. Or select a button, choose **Shortcut** when using native
Resolve mode, and click **Record shortcut…**. Press your combination in the
recording area, click **Use shortcut**, then **Apply & save**. Recording fills
the field for review; it captures one combination, rather than a timed sequence.
Esc cancels recording; type `Esc` manually if you want to assign Escape.

Shortcuts assume a US-style keyboard layout. Supported Windows keys include
letters, digits, F1–F24, navigation keys, numpad keys, media keys, and Ctrl, Alt,
Shift and Super modifiers. `Super`, `Win` and `Windows` mean the Windows key.
Common punctuation can be entered literally or by name:

| Key | Name |
| --- | --- |
| `,` / `.` / `/` | `Comma` / `Dot` (or `Period`) / `Slash` |
| `;` / `'` | `Semicolon` / `Apostrophe` |
| `[` / `]` / `\` | `LeftBracket` / `RightBracket` / `Backslash` |
| `-` / `=` | `Minus` / `Equal` |
| Backtick | `Grave` (or `Backtick`) |

The `+` character separates keys. For the shifted plus key, enter
`Ctrl+Shift+Equal`, for example. The legacy name `Plus` still means the physical
equals/plus key without adding Shift. Other shifted punctuation similarly uses
Shift plus its base key; the recorder writes this explicitly.

Unsupported key names are rejected without replacing the saved profile. Some
system shortcuts may be intercepted by Windows or the desktop before the recorder
receives them; enter those by name. In native Resolve mode, JOG, SCRL and SHTL
are reserved for the native wheel, and recording is available only for buttons
set to Shortcut.

Hold-to-repeat, held modifiers, arbitrary shell commands and automatic
application-based profile switching are not implemented. See
[KEYMAP.md](KEYMAP.md) for the physical button IDs and starter shortcuts.

## Linux desktop setup and future Resolve support

The original Linux desktop backend is still included. It uses **hidraw/sysfs**
for the controller and **evdev/uinput** for keyboard/scroll output.

Requirements: Python 3.10+, tkinter, venv support, a C compiler and Python/Linux
input development headers for evdev, plus systemd/udev and `setfacl` for device
access. Install them with your distribution's package manager, then:

```sh
git clone https://github.com/russellmm/SpeedEditor.git
cd SpeedEditor
./setup.sh
sudo bash ./install-device-access.sh
./run.sh doctor
./run.sh
```

Device-access setup runs once. It installs
`/etc/udev/rules.d/70-speededitor.rules` and grants the active local user access
to this USB HID device and `/dev/uinput`. Reconnect USB if needed; run the app
itself as your normal user. To undo setup, remove that rule, reload udev rules
and reboot.

The **combined native Resolve wheel plus custom buttons mode is currently
Windows-only**. A future Linux port needs Linux equivalents of the HID-read
routing and foreground-process checks, integration with the existing uinput
output, and testing in a real Linux Resolve session. It is not enabled by merely
installing Frida on Linux. The current backend stops desktop mapping when it
detects Resolve, allowing normal native Resolve operation without custom remaps.

## Troubleshooting

- **`Short USB output report` on Monitor only:** reopen the app and check for
  v0.1.0 or later beside its name. Earlier builds incorrectly rejected successful
  padded Windows LED writes. Genuine short writes and device errors still fail.
- **USB connected, interface busy/restricted:** Resolve can hold the interface
  exclusively. This is expected when using the Windows native-wheel adapter.
  Desktop mapping requires Resolve to be closed.
- **`doctor` returns exit code 1 while Resolve is open:** its standalone USB
  access check can fail because Resolve owns the device. That does not by itself
  mean the runtime adapter cannot connect.
- **A button still behaves natively:** confirm that it is set to Shortcut,
  saved, and mapping is active. Give Resolve focus and move the wheel briefly.
- **Attachment fails:** check that one Resolve instance is running and another
  SpeedEditor adapter is not already connected. Stop/reconnect after a Resolve
  restart or device reconnection.
- **Shortcuts do not arrive:** verify the shortcut in Resolve's current keyboard
  layout. Windows can block input delivery to a process running with higher
  privileges; normally run both applications without elevation.
- **Battery unavailable while Resolve runs:** Windows defers battery queries
  while Resolve owns the controller. It does not display a stale percentage.

The runtime adapter temporarily hooks Resolve's input path. It does not patch
the application on disk, install a USB filter driver or change device firmware.
A short lease restores native button handling if the adapter host stops
responding. This remains experimental software tied to the observed input path;
other Resolve builds, pages and button/shortcut combinations need more testing.

## Verification and development

The Windows GUI live check confirmed **CAM9 → Space** alongside normal native
JOG/SCRL/SHTL. Other remaps and standalone Windows desktop delivery have not all
been verified. Detailed results and limitations are in
[VERIFICATION.md](VERIFICATION.md).

The automated test suite passes on Windows and Ubuntu WSL with platform-specific
skips. Windows GUI behavior checks run with hidden windows; Linux rendering
checks use Xvfb at normal and high DPI. Node.js is optional for the JavaScript
adapter tests; it is not needed to run the GUI.

Windows:

```powershell
.\.venv-win\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv-win\Scripts\python.exe -m unittest discover -s tests -v
.\.venv-win\Scripts\python.exe tests/gui_smoke.py --headless
.\.venv-win\Scripts\python.exe tests/gui_smoke.py --headless --high-dpi
.\SpeedEditor.cmd doctor
.\SpeedEditor.cmd monitor --native-resolve --profile profiles/resolve-native.json --seconds 30
```

Linux, with Xvfb and xauth installed:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
xvfb-run -a .venv/bin/python tests/gui_smoke.py
xvfb-run -a .venv/bin/python tests/gui_smoke.py --high-dpi
```

Generated screenshots, local captures and logs stay in the ignored `artifacts/`
directory. Published measurement summaries are in `docs/`. Development notes:
[Windows port](docs/WINDOWS_PORT.md) and
[Resolve adapter](docs/RESOLVE_ADAPTER.md).

## Attribution

USB authentication uses Sylvain Munaut's published Speed Editor protocol code.
Its original sources, Apache-2.0 license and notices are retained in
[third_party/](third_party/NOTICE.md).

This independent project is not affiliated with or endorsed by Blackmagic Design.
