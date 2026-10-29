import argparse
from datetime import datetime
import math
import os
from pathlib import Path
import queue
import time

from .device import discover, resolve_running
from . import __version__
from .mapping import ROOT, load_profile


def main():
    parser = argparse.ArgumentParser(description='SpeedEditor USB key mapper')
    parser.add_argument('--version', action='version', version=f'SpeedEditor {__version__}')
    parser.add_argument('command', choices=['gui', 'doctor', 'monitor', 'map', 'capture-native'], nargs='?', default='gui')
    parser.add_argument('--profile', type=Path, default=ROOT / 'profiles/desktop.json')
    parser.add_argument('--seconds', type=float, help='Stop monitor or map after this many seconds')
    parser.add_argument('--output', type=Path, help='JSONL path for passive native capture')
    parser.add_argument('--native-resolve', action='store_true', help='Use experimental Resolve button routing with native wheel (Windows)')
    args = parser.parse_args()
    if args.seconds is not None and (not math.isfinite(args.seconds) or args.seconds <= 0):
        parser.error('--seconds must be a finite positive number')
    if args.command == 'capture-native':
        if os.name != 'nt':
            parser.error('capture-native currently requires Windows Raw Input')
        from .native_capture import capture
        path = args.output or ROOT / 'artifacts' / f'native-{datetime.now():%Y%m%d-%H%M%S}.jsonl'
        try:
            count = capture(path, args.seconds or 180)
        except OSError as error:
            print(f'Passive capture unavailable: {error}')
            print('Resolve may hide the collection while it owns the device. No controller settings were changed.')
            return 1
        return 0 if count else 1
    if args.command == 'gui':
        from .app import main as gui_main
        gui_main()
        return 0
    if args.command == 'doctor':
        print(f'SpeedEditor {__version__}')
        devices = discover()
        print('Speed Editor:', devices or 'not found')
        output_access = os.name == 'nt' or os.access('/dev/uinput', os.W_OK)
        print('Keyboard output:', 'Windows SendInput (no test shortcuts sent)' if os.name == 'nt'
              else f'Linux uinput access: {output_access}')
        print('Resolve running:', resolve_running())
        for profile in sorted((ROOT / 'profiles').glob('*.json')):
            print(f'Profile {profile.name}: {load_profile(profile)["name"]} — valid')
        return 0 if devices and all(d['accessible'] for d in devices) and output_access else 1
    from .worker import Worker
    worker = Worker()
    worker.start(load_profile(args.profile), args.command == 'map', native_resolve=args.native_resolve)
    deadline = time.monotonic() + args.seconds if args.seconds else float('inf')
    failed = False
    try:
        while True:
            if time.monotonic() >= deadline:
                worker.stop()
            try:
                kind, data = worker.events.get(timeout=0.2)
            except queue.Empty:
                continue
            print(kind, data, flush=True)
            if kind == 'error':
                failed = True
            if kind == 'stopped':
                break
    except KeyboardInterrupt:
        worker.stop()
    finally:
        worker.stop()
        worker.thread.join(timeout=3)
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
