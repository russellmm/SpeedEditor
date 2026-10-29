"""Passive Windows Raw Input recorder; never opens or writes to the controller."""
import ctypes as c
from ctypes import wintypes as w
from datetime import datetime, timezone
import json
from pathlib import Path
import struct
import time


def capture(path, seconds=180):
    from .device import parse_report
    user = c.WinDLL('user32', use_last_error=True)
    kernel = c.WinDLL('kernel32', use_last_error=True)
    pointer = c.c_size_t
    callback_type = c.WINFUNCTYPE(c.c_ssize_t, w.HWND, w.UINT, pointer, c.c_ssize_t)

    class DeviceList(c.Structure):
        _fields_ = [('handle', w.HANDLE), ('type', w.DWORD)]

    class Registration(c.Structure):
        _fields_ = [('page', w.USHORT), ('usage', w.USHORT),
                    ('flags', w.DWORD), ('target', w.HWND)]

    class WindowClass(c.Structure):
        _fields_ = [('style', w.UINT), ('callback', callback_type),
                    ('class_extra', c.c_int), ('window_extra', c.c_int),
                    ('instance', w.HINSTANCE), ('icon', w.HICON),
                    ('cursor', w.HANDLE), ('background', w.HBRUSH),
                    ('menu', w.LPCWSTR), ('name', w.LPCWSTR)]

    class Header(c.Structure):
        _fields_ = [('type', w.DWORD), ('size', w.DWORD),
                    ('device', w.HANDLE), ('param', pointer)]

    user.GetRawInputDeviceList.argtypes = [c.POINTER(DeviceList), c.POINTER(w.UINT), w.UINT]
    user.GetRawInputDeviceList.restype = w.UINT
    user.GetRawInputDeviceInfoW.argtypes = [w.HANDLE, w.UINT, w.LPVOID, c.POINTER(w.UINT)]
    user.GetRawInputDeviceInfoW.restype = w.UINT
    user.GetRawInputData.argtypes = [w.HANDLE, w.UINT, w.LPVOID, c.POINTER(w.UINT), w.UINT]
    user.GetRawInputData.restype = w.UINT
    user.PeekMessageW.argtypes = [c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT]
    user.TranslateMessage.argtypes = [c.POINTER(w.MSG)]
    user.DispatchMessageW.argtypes = [c.POINTER(w.MSG)]
    user.DispatchMessageW.restype = c.c_ssize_t
    user.DefWindowProcW.argtypes = [w.HWND, w.UINT, pointer, c.c_ssize_t]
    user.DefWindowProcW.restype = c.c_ssize_t
    user.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                                   c.c_int, c.c_int, c.c_int, c.c_int,
                                   w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID]
    user.CreateWindowExW.restype = w.HWND
    user.RegisterClassW.argtypes = [c.POINTER(WindowClass)]
    user.RegisterRawInputDevices.argtypes = [c.POINTER(Registration), w.UINT, w.UINT]
    user.DestroyWindow.argtypes = [w.HWND]
    user.UnregisterClassW.argtypes = [w.LPCWSTR, w.HINSTANCE]
    kernel.GetModuleHandleW.argtypes = [w.LPCWSTR]
    kernel.GetModuleHandleW.restype = w.HMODULE
    count = w.UINT()
    if user.GetRawInputDeviceList(None, c.byref(count), c.sizeof(DeviceList)) == 0xffffffff:
        raise c.WinError(c.get_last_error())
    devices = (DeviceList * count.value)()
    if user.GetRawInputDeviceList(devices, c.byref(count), c.sizeof(DeviceList)) == 0xffffffff:
        raise c.WinError(c.get_last_error())
    selected = {}
    usages = set()
    for device in devices:
        length = w.UINT(1024)
        name = c.create_unicode_buffer(1024)
        user.GetRawInputDeviceInfoW(device.handle, 0x20000007, name, c.byref(length))
        if 'vid_1edb&pid_da0e' not in name.value.lower():
            continue
        info = c.create_string_buffer(32)
        struct.pack_into('<I', info, 0, 32)
        length = w.UINT(32)
        if user.GetRawInputDeviceInfoW(device.handle, 0x2000000b, info, c.byref(length)) == 0xffffffff:
            raise c.WinError(c.get_last_error())
        page, usage = struct.unpack_from('<HH', info, 20)
        usages.add((page, usage))
        selected[device.handle] = name.value
    if not selected:
        raise OSError('No Speed Editor Raw Input collection found; check USB connection.')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    mode = 'UNKNOWN'
    held = set()
    errors = []
    report_count = 0
    with path.open('w', encoding='utf-8') as stream:
        def record(event):
            stream.write(json.dumps(event) + '\n')
            stream.flush()

        record({'kind': 'session', 'utc': datetime.now(timezone.utc).isoformat(),
                'source': 'Windows Raw Input', 'passive': True,
                'devices': list(selected.values()), 'usages': sorted(usages),
                'limitations': 'Input reports only; mode inferred from observed button presses. '
                               'No host output/feature traffic or Resolve timeline measurements.'})

        @callback_type
        def callback(hwnd, message, wp, lp):
            nonlocal mode, held, report_count
            try:
                if message == 0xff:  # WM_INPUT
                    size = w.UINT()
                    user.GetRawInputData(w.HANDLE(lp), 0x10000003, None, c.byref(size), c.sizeof(Header))
                    data = c.create_string_buffer(size.value)
                    result = user.GetRawInputData(w.HANDLE(lp), 0x10000003, data, c.byref(size), c.sizeof(Header))
                    if result == 0xffffffff:
                        raise c.WinError(c.get_last_error())
                    header = Header.from_buffer_copy(data)
                    if header.device in selected and header.type == 2:
                        width, n = struct.unpack_from('<II', data, c.sizeof(Header))
                        for index in range(n):
                            offset = c.sizeof(Header) + 8 + index * width
                            raw = data.raw[offset:offset + width]
                            parsed = parse_report(raw)
                            if parsed and parsed[0] == 'keys':
                                current = parsed[1]
                                for key in sorted(current - held):
                                    mode = {0x1c: 'SHTL', 0x1d: 'JOG', 0x1e: 'SCRL'}.get(key, mode)
                                held = current
                            record({'kind': 'report', 't': round(time.monotonic() - start, 6),
                                    'mode': mode, 'raw': raw.hex(),
                                    'parsed': [parsed[0], sorted(parsed[1]) if parsed[0] == 'keys' else parsed[1]] if parsed else None})
                            report_count += 1
            except Exception as error:
                errors.append(str(error))
            return user.DefWindowProcW(hwnd, message, wp, lp)

        instance = kernel.GetModuleHandleW(None)
        name = f'SpeedEditorPassiveCapture{time.monotonic_ns()}'
        window_class = WindowClass(0, callback, 0, 0, instance, None, None, None, None, name)
        if not user.RegisterClassW(c.byref(window_class)):
            raise c.WinError(c.get_last_error())
        hwnd = None
        registrations = []
        try:
            hwnd = user.CreateWindowExW(0, name, name, 0, 0, 0, 0, 0, w.HWND(-3), None, instance, None)
            if not hwnd:
                raise c.WinError(c.get_last_error())
            # This controller exposes usage 0. Register the vendor usage page
            # with PAGEONLY, then filter incoming messages by device handle.
            registrations = (Registration * len(usages))(*(Registration(p, u, 0x100 | (0x20 if u == 0 else 0), hwnd) for p, u in usages))
            if not user.RegisterRawInputDevices(registrations, len(usages), c.sizeof(Registration)):
                raise c.WinError(c.get_last_error())
            print(f'Passive capture ready for {seconds:g}s: {path}', flush=True)
            message = w.MSG()
            try:
                while time.monotonic() - start < seconds and not path.with_suffix('.stop').exists():
                    while user.PeekMessageW(c.byref(message), None, 0, 0, 1):
                        user.TranslateMessage(c.byref(message))
                        user.DispatchMessageW(c.byref(message))
                    if errors:
                        raise OSError(errors[0])
                    time.sleep(0.005)
            except KeyboardInterrupt:
                pass
        finally:
            for registration in registrations if hwnd else []:
                registration.flags, registration.target = 1, None  # RIDEV_REMOVE
                user.RegisterRawInputDevices(c.byref(registration), 1, c.sizeof(Registration))
            if hwnd:
                user.DestroyWindow(hwnd)
            user.UnregisterClassW(name, instance)
            record({'kind': 'end', 'reports': report_count, 'elapsed': time.monotonic() - start,
                    'errors': errors})
    print(f'Capture complete: {report_count} reports', flush=True)
    return report_count
