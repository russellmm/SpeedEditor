"""Read battery feature reports without authenticating or enabling mappings."""
import threading
import os

from .device import Device, discover, resolve_running


class BatteryMonitor:
    def __init__(self, events, interval=5):
        self.events = events
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = None

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def check(self):
        device = None
        try:
            if os.name == 'nt' and resolve_running():
                return 'battery_unavailable', 'Battery: unavailable while Resolve owns controller'
            devices = discover()
            if not devices:
                return 'battery_unavailable', 'Battery: disconnected'
            if len(devices) > 1:
                return 'battery_unavailable', 'Battery: multiple devices connected'
            if not devices[0]['accessible']:
                return 'battery_unavailable', 'Battery: interface busy or access required'
            device = Device(devices[0]['path'])
            return 'battery', device.battery_status()
        except (OSError, ValueError):
            return 'battery_unavailable', 'Battery: unavailable'
        finally:
            if device:
                # A battery-only query must not alter wheel LEDs or the auth state.
                try:
                    device.close(clear_leds=False)
                except OSError:
                    pass

    def run(self):
        while not self.stop_event.is_set():
            self.events.put(self.check())
            if self.stop_event.wait(self.interval):
                break
