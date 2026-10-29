"""One worker owns the device; all GUI communication uses queues."""
from copy import deepcopy
import queue
import threading
import time

from .device import Device, discover, parse_report, resolve_running
from .mapping import Mapper, VirtualOutput


class Worker:
    def __init__(self):
        self.events = queue.Queue()
        self.commands = queue.Queue()
        self.thread = None
        self.stop_event = threading.Event()

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, profile, active=False, native_resolve=False):
        if self.running:
            raise RuntimeError('Stop the current session first')
        self.stop_event.clear()
        while not self.commands.empty():
            self.commands.get_nowait()
        self.thread = threading.Thread(target=self.run, args=(deepcopy(profile), active, native_resolve), daemon=True)
        self.thread.start()

    def update(self, profile):
        self.commands.put(deepcopy(profile))

    def stop(self):
        self.stop_event.set()

    def run(self, profile, active, native_resolve=False):
        if native_resolve:
            from .resolve_bridge import ResolveBridge
            ResolveBridge(self.events, self.commands, self.stop_event).run(profile, active)
            return
        device = output = mapper = None
        try:
            if resolve_running():
                raise RuntimeError('Resolve is running. Use “Use native Resolve” to let it own the controller.')
            devices = discover()
            if not devices:
                raise RuntimeError('Connect the Speed Editor by USB and try again.')
            if len(devices) > 1:
                raise RuntimeError('Multiple Speed Editors found. Connect only one for this version.')
            if not devices[0]['accessible']:
                raise PermissionError(devices[0].get('reason') or
                                      'Device access is restricted. Run the device-access setup once.')
            device = Device(devices[0]['path'])
            delay = device.authenticate()
            output = VirtualOutput() if active else None
            mapper = Mapper(profile, output.emit if output else lambda action: None)
            self.configure_wheel(device, mapper)
            next_auth = time.monotonic() + delay
            next_resolve_check = time.monotonic() + 1
            self.events.put(('status', 'Mapping active' if active else 'Monitor connected — no shortcuts sent'))
            while not self.stop_event.is_set():
                now = time.monotonic()
                if now >= next_resolve_check:
                    if resolve_running():
                        self.events.put(('status', 'Released controller for native Resolve'))
                        break
                    next_resolve_check = now + 1
                if now >= next_auth:
                    mapper.stop()
                    delay = device.authenticate()
                    self.configure_wheel(device, mapper)
                    mapper.remainder = 0
                    next_auth = now + delay
                while True:
                    try:
                        updated = self.commands.get_nowait()
                    except queue.Empty:
                        break
                    previous_held, previous_mode = mapper.held, mapper.mode
                    mapper.stop()
                    mapper = Mapper(updated, output.emit if output else lambda action: None)
                    mapper.held, mapper.mode = previous_held, previous_mode
                    self.configure_wheel(device, mapper)
                report = parse_report(device.read(), wheel_mode=mapper.hardware_mode)
                if report is None:
                    continue
                kind, data = report
                if kind == 'keys':
                    old_mode = mapper.mode
                    events = mapper.buttons(data)
                    if mapper.mode != old_mode:
                        self.configure_wheel(device, mapper)
                    self.events.put(('keys', (data, events, mapper.mode)))
                elif kind == 'wheel':
                    action, count = mapper.wheel(data)
                    self.events.put(('wheel', (data, action, count, mapper.mode)))
                else:
                    self.events.put(('battery', data))
        except Exception as error:
            self.events.put(('error', f'{type(error).__name__}: {error}'))
        finally:
            if mapper:
                try:
                    mapper.stop()
                except OSError:
                    pass
            if output:
                try:
                    output.close()
                except OSError:
                    pass
            if device:
                try:
                    device.close()
                except OSError:
                    pass
            self.events.put(('stopped', None))

    @staticmethod
    def configure_wheel(device, mapper):
        if mapper.hardware_mode:
            device.configure_wheel(mapper.mode, mapper.hardware_mode)
        else:
            device.relative_wheel(mapper.mode)
