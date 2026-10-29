# Resolve button overrides with the native wheel — experimental

Windows 11 / USB Speed Editor / observed Resolve build **21.1.0.14**.

This mode keeps Resolve responsible for authentication, LEDs, wheel modes,
speed response, neutral origins and context-specific navigation. It changes
only explicitly overridden button entries in the input reports Resolve receives,
then sends their programmed keyboard/scroll shortcuts through Windows SendInput.
It is a third-party runtime adapter, not an official Blackmagic plugin/API.

## GUI workflow

Run `setup.ps1` to install dependencies, then open `SpeedEditor.cmd`.
Select the **Resolve native wheel** profile, which selects **Resolve native wheel
(experimental)** as the control mode. The app remains disconnected initially.

- **Native**: pass that button through unchanged. This is the default for all buttons.
- **Shortcut**: suppress that button's native action and tap its assigned shortcut.
- **Disabled**: suppress that button without sending a shortcut.

JOG, SCRL and SHTL stay native and their override controls are disabled. Wheel
shortcut fields and sensitivity controls are also disabled in this mode. The
remaining 40 buttons, including STOP/PLAY, can be explicitly overridden.

**Monitor only** attaches without replacing reports or creating keyboard output.
**Start mapping** enables the saved overrides. Return to Resolve and move the
wheel briefly so a completed read arms the adapter. Shortcuts apply only while
Resolve has focus. **Stop adapter** or **Use native Resolve** detaches it and
restores native buttons; use Resolve's native controls to stop playback itself.

The existing Desktop and Resolve shortcuts profiles retain their desktop button
and Standard/Custom wheel settings. Those settings are not implicitly imported
as native-wheel button overrides. You may use any profile in either control mode.

## Saved profile representation

```json
"resolve_buttons": {
  "CAM9": "Space",
  "CAM1": ""
}
```

The CAM9 override replaces its native action with play/pause. CAM1 is disabled;
all omitted buttons remain native. Choosing Native deletes that entry. No
schema-version bump is required; older profiles without this optional field
remain valid. `preferred_control_mode: "resolve_native"` selects this view on
loading a profile while disconnected.

## Runtime boundary

`speededitor/resolve_bridge.py` attaches the local Frida 17.23.2 runtime to the
single running Resolve.exe instance and loads `resolve_bridge.js`. A named
Windows object prevents two SpeedEditor adapters from attaching to the same PID.

The script verifies HID vendor/product 1edb:da0e through the existing handle. It
observes ReadFile and GetOverlappedResult/GetOverlappedResultEx completions, plus
HidD_GetInputReport. For report 4, explicitly overridden key slots are removed
before Resolve consumes the report. Releases and other native keys are preserved.
Wheel report 3 and all host output/feature traffic remain untouched. Unknown
buttons and reports pass through. The script issues no controller output calls.

The worker renews a 1.5-second lease every 0.3 seconds. When the lease expires,
Resolve loses focus, an adapter fault occurs, or mapping is disabled, the routing
path passes native buttons through. Press edges produce one shortcut per press.
Profile updates wait until held buttons are released. Windows foreground PID is
checked again before asynchronous shortcut delivery, and Stop disables routing
before unloading/detaching the script.

This is built around the input path observed on this Resolve build. Alternate
completion mechanisms, future application updates, permissions, process exits
and device reconnections may require stopping/restarting or updating the adapter.
It does not patch files on disk, install a USB filter driver, or emulate the
native speed curve. Native behavior comes from Resolve receiving the original
wheel and wheel-mode reports.

## Verification so far

- Production worker attached to running Resolve in Monitor only; 240 wheel
  updates and eight key reports were received. The user confirmed native JOG,
  SCRL and SHTL continued normally. That session was detached.
- The actual script loaded in the Windows Frida runtime with real-device
  routing disabled. Its synthetic-report RPC preserved wheel bytes and monitor
  key reports, removed mapped CAM9 while retaining JOG, and produced the expected
  synthetic Space action. No keyboard event was sent by this check.
- JavaScript tests execute the actual routing functions and mocked real hooks:
  synchronous/asynchronous reads, reserved modes, disabled buttons, unknown keys,
  repeated presses/releases, focus gating, lease expiry and disabling routing.
- Python tests cover profile separation, reserved-mode validation, worker
  cleanup on faults/input failure, focus recheck, queue overflow and one-instance
  locking. GUI tests verify Native/Shortcut/Disabled edits and profile selection.
- Windows GUI checks use hidden windows. Linux rendered GUI checks use Xvfb.

**Live check passed:** the user opened the prepared GUI profile, started mapping,
and confirmed CAM9 → Space toggled play/pause while JOG, SCRL and SHTL continued
to work natively in Resolve. This verifies the combined path for that button,
shortcut and context; it does not validate every shortcut or Resolve page.

The app stays disconnected or in Monitor only until the user starts mapping.
The ignored `artifacts/resolve-native-live-check.json` has CAM9 → Space and all
other buttons Native. The user-started GUI session may stay active; Stop adapter
restores native button handling. The agent's temporary monitor/runtime probes
were detached before the GUI check. No unrequested Resolve edits are automated.
