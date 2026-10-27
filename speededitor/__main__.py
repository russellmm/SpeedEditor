import argparse
import os
from pathlib import Path
import queue
import time

from .device import discover, resolve_running
from .mapping import ROOT, load_profile


def main():
    parser = argparse.ArgumentParser(description='SpeedEditor USB key mapper')
    parser.add_argument('command', choices=['gui', 'doctor', 'monitor', 'map'], nargs='?', default='gui')
    parser.add_argument('--profile', type=Path, default=ROOT / 'profiles/desktop.json')
    parser.add_argument('--seconds', type=float, help='Stop monitor or map after this many seconds')
    args = parser.parse_args()
    if args.command == 'gui':
        from .app import main as gui_main
        gui_main()
        return 0
    if args.command == 'doctor':
        devices = discover()
        print('Speed Editor:', devices or 'not found')
        print('Virtual keyboard access:', os.access('/dev/uinput', os.W_OK))
        print('Resolve running:', resolve_running())
        for profile in sorted((ROOT / 'profiles').glob('*.json')):
            print(f'Profile {profile.name}: {load_profile(profile)["name"]} — valid')
        return 0 if devices and all(d['accessible'] for d in devices) and os.access('/dev/uinput', os.W_OK) else 1
    from .worker import Worker
    worker = Worker()
    worker.start(load_profile(args.profile), args.command == 'map')
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
