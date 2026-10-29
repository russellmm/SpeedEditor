"""Windows HIDAPI transport; Resolve may hold the interface exclusively."""
import ctypes
from ctypes import wintypes
import uuid


def interface_paths():
    """List present HID paths even when an exclusive owner prevents HIDAPI enumeration."""
    manager = ctypes.WinDLL('cfgmgr32', use_last_error=True)
    manager.CM_Get_Device_Interface_List_SizeW.argtypes = [ctypes.POINTER(wintypes.ULONG),
                                                         ctypes.c_void_p, wintypes.LPCWSTR, wintypes.ULONG]
    manager.CM_Get_Device_Interface_ListW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR,
                                                    wintypes.LPWSTR, wintypes.ULONG, wintypes.ULONG]
    guid = ctypes.create_string_buffer(uuid.UUID('4d1e55b2-f16f-11cf-88cb-001111000030').bytes_le, 16)
    for _ in range(3):  # Device arrival can change the list between the two calls.
        size = wintypes.ULONG()
        result = manager.CM_Get_Device_Interface_List_SizeW(ctypes.byref(size), guid, None, 0)
        if result:
            raise OSError(f'Cannot enumerate HID interfaces (Configuration Manager {result})')
        buffer = ctypes.create_unicode_buffer(max(1, size.value))
        result = manager.CM_Get_Device_Interface_ListW(guid, None, buffer, len(buffer), 0)
        if result == 0x1a:  # CR_BUFFER_SMALL
            continue
        if result:
            raise OSError(f'Cannot enumerate HID interfaces (Configuration Manager {result})')
        return [p.encode('utf-8') for p in buffer[:].split('\0')
                if 'vid_1edb&pid_da0e' in p.lower()]
    raise OSError('HID device list changed repeatedly; try again')


def discover():
    import hid
    devices = {item['path'].lower(): {'path': item['path'],
               'name': item.get('product_string') or 'Speed Editor',
               'accessible': True} for item in hid.enumerate(0x1edb, 0xda0e)}
    for path in interface_paths():
        devices.setdefault(path.lower(), {'path': path, 'name': 'DaVinci Resolve Speed Editor',
                           'accessible': False,
                           'reason': 'Interface busy or restricted (Resolve may own it)'})
    return list(devices.values())


def resolve_process_ids():
    class ProcessEntry(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD),
                    ('pid', wintypes.DWORD), ('heap', ctypes.c_size_t),
                    ('module', wintypes.DWORD), ('threads', wintypes.DWORD),
                    ('parent', wintypes.DWORD), ('priority', wintypes.LONG),
                    ('flags', wintypes.DWORD), ('exe', wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        found = []
        entry = ProcessEntry()
        entry.size = ctypes.sizeof(entry)
        more = kernel.Process32FirstW(handle, ctypes.byref(entry))
        if not more:
            raise ctypes.WinError(ctypes.get_last_error())
        while more:
            if entry.exe.lower() == 'resolve.exe':
                found.append(entry.pid)
            more = kernel.Process32NextW(handle, ctypes.byref(entry))
        if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
            raise ctypes.WinError(ctypes.get_last_error())
        return found
    finally:
        kernel.CloseHandle(handle)


def resolve_running():
    return bool(resolve_process_ids())


def foreground_process_id():
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetForegroundWindow.restype = wintypes.HWND
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    pid = wintypes.DWORD()
    user.GetWindowThreadProcessId(user.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value


class ResolveBridgeLock:
    """Only one SpeedEditor button adapter may attach to a Resolve PID."""
    def __init__(self, pid):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        ctypes.set_last_error(0)
        self.handle = self.kernel.CreateMutexW(None, False, f'Local\\SpeedEditorResolveBridge-{pid}')
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:
            self.close()
            raise RuntimeError('A SpeedEditor Resolve adapter is already connected. Stop it before starting another.')

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class WindowsDevice:
    def __init__(self, path):
        import hid
        self.handle = hid.device()
        try:
            self.handle.open_path(path)
        except Exception:
            self.handle.close()
            self.handle = None
            raise

    def feature_get(self, rid, size=10):
        data = bytes(self.handle.get_feature_report(rid, size))
        if len(data) != size:
            raise OSError(f'Short feature report: {len(data)}/{size}')
        return data

    def feature_set(self, data):
        if self.handle.send_feature_report(data) != len(data):
            raise OSError('Short USB feature report')

    def write(self, data):
        # Windows HIDAPI pads smaller output reports to the collection's
        # longest report and returns the padded count (e.g. 2-byte LEDs → 7).
        # A count larger than the payload is therefore a successful write.
        written = self.handle.write(data)
        if written < len(data):
            raise OSError(f'Short USB output report: {written}/{len(data)} payload bytes')

    def read(self, timeout=0.1):
        return bytes(self.handle.read(64, max(0, round(timeout * 1000))))

    def close(self, clear_leds=True):
        if self.handle is not None:
            try:
                if clear_leds:
                    try:
                        self.write(bytes([4, 0]))
                    except OSError:
                        pass
            finally:
                self.handle.close()
                self.handle = None
