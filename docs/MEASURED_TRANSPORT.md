# Experimental measured desktop transport

This optional desktop wheel behavior puts the retained Windows 11 / Resolve
Cut / Source Tape observations to use. It estimates a target from wheel input
and translates that target into application shortcuts. It is not native Resolve
integration or a claim of exact Cut/Fairlight behavior.

## Set it up

1. Select **Desktop shortcuts** and a personal profile. Resolve must be closed
   so the standalone mapper can own the USB controller.
2. Choose **Measured** beside any wheel mode you want to change.
3. Open **Measured transport settings…**. Set JOG/SCRL steps per turn, the
   target editor's Stop shortcut, and your SHTL output choice.
4. For **Per-speed shortcuts**, select a speed, enter or record the editor's
   direct speed shortcut, and click **Assign**. These must be commands the
   editor actually supports. Empty or `None` assignments send only Stop.
5. Click **Save settings**. This saves both the dialog settings and the current
   wheel behavior choices. Cancel discards staged dialog edits.
6. Use **Monitor only** first. After reviewing input and targets, click Stop,
   focus your editor, and start mapping when ready.

**Save wheel settings** also saves behavior choices. Measured modes ignore the
ordinary threshold field. JOG/SCRL still use their left/right shortcut fields;
SHTL instead uses the selected output policy. Standard remains the starter
profile default, and legacy Custom profiles retain their original behavior.

For Resolve while it is running, select **Resolve native wheel (experimental)**.
That adapter passes the original wheel reports to Resolve. Desktop Measured
settings do not alter that adapter or let the standalone mapper share Resolve's
USB connection.

## What comes from the captures

| Mode | Measured input | User setting / approximation |
| --- | --- | --- |
| JOG | Hardware mode 2; approximately 1,470,741 units per turn, averaging the clockwise/counterclockwise trial magnitudes | Steps per turn defaults to 60; native frames per turn were not measured |
| SCRL | Hardware mode 2; approximately 1,468,558 units per turn, including the overshoot correction | Steps per turn defaults to 600; native search gain was not measured |
| SHTL | Absolute hardware mode 3; retained signed plateau samples through ±4096, plus the observed stop/neutral rules | Nearest-sample lookup estimates the target; exact transition boundaries remain unknown |

The source ledger is [shuttle-curve-2026-10-28.json](data/shuttle-curve-2026-10-28.json).
Multiple positions for the same signed rate are aggregated by their median.
Each direction is compared with its own sample positions and zero. The nearest
position selects a rate; ties favor the lower magnitude. This creates estimated
midpoint boundaries, not measured native thresholds. Unsampled reverse rates
are not fabricated by symmetry, so reverse has fewer distinct target levels.

Measured SHTL consumes absolute positions, never summed deltas. Playback remains
latched with a stationary wheel. Re-pressing SHTL stops without reprogramming the
hardware or changing neutral; the same stationary position cannot restart it.
Further movement resumes according to the retained neutral. Leaving SHTL through
JOG/SCRL and returning programs mode 3 again, establishing a new zero.

Mode changes, profile updates, authentication renewal and stopping/disconnecting
the mapper stop latched transport. Profile updates and authentication renewal
also reconfigure the hardware, so a new SHTL neutral is established. Wheel reports
from a different hardware mode are ignored during transitions. Values outside
the captured ±4096 absolute range are ignored. Relative step output is capped
at 80 actions per report; excess steps in a burst are discarded rather than queued.

## SHTL application output

**Approximate J/K/L** is the initial output setting. It selects the nearest
nominal rate from 1, 2, 4, 8, 16, 32 and 64 using logarithmic distance, with ties
favoring the lower rate. Stop is sent before J/L taps when that output level
changes. An idle wheel or a target change within the same output level does not
send more speed-up taps. The editor must use repeated J/L taps for its transport;
its actual levels and limits may differ from those nominal rates.

For example, a captured **+0.25× target** sends Stop and one L tap, which is
typically a normal-speed keyboard command rather than quarter-speed playback.
The log says `Measured target +0.25× → approximate J/K/L level 1 (nominal 1×)`.
A **+3× target** selects nominal 4×. These are explicit keyboard approximations.

**Per-speed shortcuts** sends Stop followed by one shortcut for that signed
target. Configure direct rate-selection commands in the target editor. The app
cannot create a playback rate the editor does not expose. Blank rates send Stop
and log `unassigned; stopped`, rather than borrowing another rate's shortcut.
Stop is configurable for both output policies and for measured JOG/SCRL stepping.
Each nonempty left/right step sends the configured stop shortcut before that
report's step actions.

## Profile storage

Each selected wheel mode uses `"behavior": "measured"`. Application settings live
in the optional top-level `measured_transport` field, independently of native
Resolve button overrides. For example:

```json
"measured_transport": {
  "output": "shortcuts",
  "stop": "K",
  "steps_per_turn": {"JOG": 60, "SCRL": 600},
  "shuttle_actions": {
    "0.25": "Ctrl+Alt+1",
    "-0.25": "Ctrl+Alt+2"
  }
}
```

The shortcut examples are placeholders for commands you assign in your editor.
They are not verified Resolve defaults. Positive/negative speed strings must
name a rate present in the sample ledger. The recorder captures a combination;
it does not emit keys or create a timed macro.

Automated tests cover the ledger samples, calibration, absolute versus relative
input, retained neutral, stale reports, bounded output, stopping, profile
compatibility and GUI editing. Real desktop mode-2/mode-3 operation and delivery
inside an editor still need a live check with Resolve stopped.
