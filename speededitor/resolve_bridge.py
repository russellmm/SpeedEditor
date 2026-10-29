"""Experimental Windows button routing while Resolve owns the native wheel."""
from copy import deepcopy
import os
from pathlib import Path
import queue
import time

from .mapping import KEYS, MODES, validate
from .windows_hid import ResolveBridgeLock, foreground_process_id, resolve_process_ids
from .windows_output import WindowsOutput


SCRIPT_PATH = Path(__file__).with_suffix('.js')


def native_rules(profile):
    validate(profile)
    overrides = profile.get('resolve_buttons', {})
    return {str(code): overrides[name] for code, name in KEYS.items() if name in overrides}


class ResolveBridge:
    def __init__(self, events, commands, stop_event):
        self.events, self.commands, self.stop_event = events, commands, stop_event
        self.incoming = queue.Queue(maxsize=1024)

    def message(self, message, _data=None):
        if message.get('type') == 'error':
            payload = {'kind': 'fault', 'error': message.get('description', 'Resolve adapter script failed')}
        elif message.get('type') == 'send' and isinstance(message.get('payload'), dict):
            payload = message['payload']
        else:
            return
        try:
            self.incoming.put_nowait(payload)
        except queue.Full:
            # The script's short lease restores native pass-through if the host
            # cannot keep up. The worker also detaches as soon as it sees stop.
            self.events.put(('error', 'Resolve event queue overflow; stopping the adapter'))
            self.stop_event.set()

    def detached(self, reason, *_args):
        self.message({'type': 'send', 'payload': {'kind': 'fault', 'error': f'Resolve detached: {reason}'}})

    def run(self, profile, active=False):
        session = script = output = lock = None
        try:
            if os.name != 'nt':
                raise RuntimeError('Resolve native-wheel routing currently requires Windows 11')
            try:
                import frida
            except ImportError as error:
                raise RuntimeError('Run setup.ps1 to install the Resolve runtime adapter') from error
            pids = resolve_process_ids()
            if len(pids) != 1:
                raise RuntimeError('Open one DaVinci Resolve instance before connecting this mode')
            pid = pids[0]
            lock = ResolveBridgeLock(pid)
            profile = deepcopy(validate(profile))
            session = frida.get_local_device().attach(pid)
            session.on('detached', self.detached)
            script = session.create_script(SCRIPT_PATH.read_text(encoding='utf-8'), name='SpeedEditor Resolve buttons')
            script.on('message', self.message)
            script.load()
            output = WindowsOutput() if active else None
            script.exports_sync.configure({'rules': native_rules(profile), 'enabled': active})
            self.events.put(('status', 'Resolve adapter connected — move the wheel briefly to arm input; native wheel remains in Resolve'))
            held = set()
            mode = 'Native'
            announced = False
            pending_profile = None
            next_heartbeat = 0
            while not self.stop_event.is_set():
                while True:
                    try:
                        pending_profile = self.commands.get_nowait()
                    except queue.Empty:
                        break
                # Apply changes between physical presses, avoiding a synthetic
                # press/release when a mapping is edited while its key is held.
                if pending_profile is not None and not held:
                    profile = deepcopy(validate(pending_profile))
                    script.exports_sync.configure({'rules': native_rules(profile), 'enabled': active})
                    pending_profile = None
                if time.monotonic() >= next_heartbeat:
                    status = script.exports_sync.heartbeat()
                    if status['pid'] != pid:
                        raise RuntimeError('Resolve adapter process changed')
                    if status['armed'] and not announced:
                        self.events.put(('status', 'Resolve button mapping active — native wheel' if active
                                         else 'Resolve monitor connected — all controls remain native'))
                        announced = True
                    next_heartbeat = time.monotonic() + .3
                try:
                    message = self.incoming.get(timeout=.05)
                except queue.Empty:
                    continue
                kind = message.get('kind')
                if kind == 'fault':
                    raise RuntimeError(message.get('error', 'Resolve adapter failed'))
                if kind == 'keys':
                    previous = held
                    held = set(message['held'])
                    for code in sorted(held - previous):
                        name = KEYS.get(code)
                        if name in MODES:
                            mode = name
                    self.events.put(('keys', (held, [], mode)))
                    for action in message.get('actions', []):
                        # Focus is checked again here, after the asynchronous
                        # script message, before any shortcut reaches Windows.
                        if active and output and foreground_process_id() == pid:
                            output.emit(action['action'])
                            self.events.put(('status_action', (KEYS.get(action['key'], 'Unknown'), action['action'])))
                elif kind == 'wheel':
                    self.events.put(('native_wheel', (message['hardware_mode'], message['value'], mode)))
        except Exception as error:
            self.events.put(('error', f'{type(error).__name__}: {error}'))
        finally:
            if script:
                try:
                    script.exports_sync.configure({'rules': {}, 'enabled': False})
                except Exception:
                    pass
                try:
                    script.unload()
                except Exception:
                    pass
            if session:
                try:
                    session.detach()
                except Exception:
                    pass
            if output:
                output.close()
            if lock:
                lock.close()
            self.events.put(('stopped', None))
