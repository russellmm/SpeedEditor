"""USB HID transport. No firmware changes or USB interface detachment."""
import os
from pathlib import Path
import select
import struct

if os.name != 'nt':
    import fcntl

from .bmd_protocol import bmd_kbd_auth


def discover():
    if os.name == 'nt':
        from .windows_hid import discover as windows_discover
        return windows_discover()
    devices = []
    for item in sorted(Path('/sys/class/hidraw').glob('hidraw*')):
        info = dict(line.split('=', 1) for line in
                    (item / 'device/uevent').read_text().splitlines() if '=' in line)
        if info.get('HID_ID') == '0003:00001EDB:0000DA0E':
            node = Path('/dev') / item.name
            devices.append({'path': str(node), 'name': info.get('HID_NAME', ''),
                            'accessible': os.access(node, os.R_OK | os.W_OK)})
    return devices


def resolve_running():
    if os.name == 'nt':
        from .windows_hid import resolve_running as windows_resolve_running
        return windows_resolve_running()
    for process in Path('/proc').glob('[0-9]*/comm'):
        try:
            if process.read_text().strip().lower() == 'resolve':
                return True
        except (OSError, UnicodeError):
            pass
    return False


class LinuxDevice:
    def __init__(self, path):
        self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)

    def feature_get(self, rid, size=10):
        data = bytearray(size)
        data[0] = rid
        request = (3 << 30) | (size << 16) | (ord('H') << 8) | 0x07
        count = fcntl.ioctl(self.fd, request, data, True)
        if count != size:
            raise OSError(f'Short feature report: {count}/{size}')
        return bytes(data)

    def feature_set(self, data):
        request = (3 << 30) | (len(data) << 16) | (ord('H') << 8) | 0x06
        fcntl.ioctl(self.fd, request, bytearray(data), True)

    def authenticate(self):
        # Adapted from Sylvain Munaut's Apache-2.0 bmd.py; see third_party/.
        self.feature_set(bytes([6, 0]) + bytes(8))
        challenge = self.feature_get(6)
        if challenge[:2] != bytes([6, 0]):
            raise RuntimeError('Speed Editor did not provide an authentication challenge')
        self.feature_set(bytes([6, 1]) + bytes(8))
        if self.feature_get(6)[:2] != bytes([6, 2]):
            raise RuntimeError('Speed Editor authentication response was unexpected')
        response = bmd_kbd_auth(int.from_bytes(challenge[2:], 'little'))
        self.feature_set(bytes([6, 3]) + response.to_bytes(8, 'little'))
        status = self.feature_get(6)
        if status[:2] != bytes([6, 4]):
            raise RuntimeError('Speed Editor authentication failed')
        timeout = int.from_bytes(status[2:4], 'little')
        return max(1, timeout - 30) if timeout else 300

    def write(self, data):
        if os.write(self.fd, data) != len(data):
            raise OSError('Short USB output report')

    def relative_wheel(self, mode='JOG'):
        self.configure_wheel(mode, 0)

    def configure_wheel(self, mode, hardware_mode):
        if mode not in ('JOG', 'SCRL', 'SHTL') or hardware_mode not in (0, 2, 3):
            raise ValueError('Invalid wheel configuration')
        self.write(struct.pack('<BBIB', 3, hardware_mode, 0, 255))
        self.write(bytes([4, {'JOG': 1, 'SHTL': 2, 'SCRL': 4}[mode]]))

    def battery_status(self):
        report = parse_report(self.feature_get(7, 3))
        if report is None or report[0] != 'battery':
            raise ValueError('Invalid battery status from Speed Editor')
        return report[1]

    def read(self, timeout=0.1):
        if not select.select([self.fd], [], [], timeout)[0]:
            return b''
        data = os.read(self.fd, 64)
        if not data:
            raise OSError('Speed Editor disconnected')
        return data

    def close(self, clear_leds=True):
        if self.fd is not None:
            if clear_leds:
                try:
                    self.write(bytes([4, 0]))
                except OSError:
                    pass
            os.close(self.fd)
            self.fd = None


def parse_report(data, wheel_mode=None):
    if not data:
        return None
    # Windows HID input buffers use the collection's maximum report size.
    # Keep the protocol payload and accept only zero padding after it.
    expected = {3: 7, 4: 13, 7: 3}.get(data[0])
    if expected and len(data) > expected and not any(data[expected:]):
        data = data[:expected]
    if data[0] == 4 and len(data) == 13:
        return 'keys', {k for k in struct.unpack('<6H', data[1:]) if k}
    if data[0] == 3 and len(data) == 7:
        if wheel_mode is not None and data[1] != wheel_mode:
            return None
        return 'wheel', struct.unpack_from('<i', data, 2)[0]
    if data[0] == 7 and len(data) == 3 and data[1] in (0, 1) and data[2] <= 100:
        return 'battery', {'charging': bool(data[1]), 'level': data[2]}
    return None


if os.name == 'nt':
    from .windows_hid import WindowsDevice

    class Device(WindowsDevice, LinuxDevice):
        """HIDAPI I/O with the shared protocol/authentication implementation."""
else:
    Device = LinuxDevice
