"""Windows keyboard/scroll output using SendInput. Creation sends nothing."""
import ctypes as c
from ctypes import wintypes as w


# Profile spelling follows the original Linux key names; values are Windows VKs.
KEY_CODES = {'KEY_' + chr(code): code for code in range(ord('A'), ord('Z') + 1)}
KEY_CODES.update({'KEY_' + str(number): ord(str(number)) for number in range(10)})
KEY_CODES.update({f'KEY_F{number}': 0x6f + number for number in range(1, 25)})
KEY_CODES.update({f'KEY_KP{number}': 0x60 + number for number in range(10)})
KEY_CODES.update({'KEY_' + name: code for name, code in {
    'BACKSPACE': 0x08, 'TAB': 0x09, 'ENTER': 0x0d, 'PAUSE': 0x13,
    'CAPSLOCK': 0x14, 'ESC': 0x1b, 'SPACE': 0x20, 'PAGEUP': 0x21,
    'PAGEDOWN': 0x22, 'END': 0x23, 'HOME': 0x24, 'LEFT': 0x25,
    'UP': 0x26, 'RIGHT': 0x27, 'DOWN': 0x28, 'SYSRQ': 0x2c,
    'INSERT': 0x2d, 'DELETE': 0x2e, 'LEFTMETA': 0x5b, 'RIGHTMETA': 0x5c,
    'COMPOSE': 0x5d, 'MENU': 0x5d, 'KPASTERISK': 0x6a, 'KPPLUS': 0x6b,
    'KPMINUS': 0x6d, 'KPDOT': 0x6e, 'KPSLASH': 0x6f,
    'NUMLOCK': 0x90, 'SCROLLLOCK': 0x91, 'LEFTSHIFT': 0xa0,
    'RIGHTSHIFT': 0xa1, 'LEFTCTRL': 0xa2, 'RIGHTCTRL': 0xa3,
    'LEFTALT': 0xa4, 'RIGHTALT': 0xa5, 'BACK': 0xa6, 'FORWARD': 0xa7,
    'REFRESH': 0xa8, 'STOP': 0xa9, 'SEARCH': 0xaa, 'FAVORITES': 0xab,
    'HOMEPAGE': 0xac, 'MUTE': 0xad, 'VOLUMEDOWN': 0xae, 'VOLUMEUP': 0xaf,
    'NEXTSONG': 0xb0, 'PREVIOUSSONG': 0xb1, 'STOPCD': 0xb2, 'PLAYPAUSE': 0xb3,
    'MAIL': 0xb4, 'MEDIA': 0xb5, 'SEMICOLON': 0xba, 'EQUAL': 0xbb,
    'COMMA': 0xbc, 'MINUS': 0xbd, 'DOT': 0xbe, 'SLASH': 0xbf,
    'GRAVE': 0xc0, 'LEFTBRACE': 0xdb, 'BACKSLASH': 0xdc,
    'RIGHTBRACE': 0xdd, 'APOSTROPHE': 0xde, '102ND': 0xe2,
}.items()})
EXTENDED_KEYS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2c,
                 0x2d, 0x2e, 0x5b, 0x5c, 0x5d, 0x6f, 0x90, 0xa3, 0xa5,
                 *range(0xa6, 0xb6)}


class KeyboardInput(c.Structure):
    _fields_ = [('vk', w.WORD), ('scan', w.WORD), ('flags', w.DWORD),
                ('time', w.DWORD), ('extra', c.c_size_t)]


class MouseInput(c.Structure):
    _fields_ = [('dx', w.LONG), ('dy', w.LONG), ('data', w.DWORD),
                ('flags', w.DWORD), ('time', w.DWORD), ('extra', c.c_size_t)]


class HardwareInput(c.Structure):
    _fields_ = [('message', w.DWORD), ('low', w.WORD), ('high', w.WORD)]


class InputUnion(c.Union):
    _fields_ = [('keyboard', KeyboardInput), ('mouse', MouseInput), ('hardware', HardwareInput)]


class Input(c.Structure):
    _anonymous_ = ('value',)
    _fields_ = [('type', w.DWORD), ('value', InputUnion)]


def keyboard_event(code, released=False):
    event = Input(type=1)
    event.keyboard = KeyboardInput(code, 0, (1 if code in EXTENDED_KEYS else 0) |
                                   (2 if released else 0), 0, 0)
    return event


class WindowsOutput:
    def __init__(self):
        self.user = c.WinDLL('user32', use_last_error=True)
        self.user.SendInput.argtypes = [w.UINT, c.POINTER(Input), c.c_int]
        self.user.SendInput.restype = w.UINT
        self.closed = False

    def _send(self, events):
        array = (Input * len(events))(*events)
        return self.user.SendInput(len(array), array, c.sizeof(Input))

    def emit(self, action):
        from .mapping import parse_action
        if self.closed:
            raise OSError('Keyboard output is closed')
        kind, codes = parse_action(action)
        if kind == 'none':
            return
        if kind == 'scroll':
            event = Input(type=0)
            event.mouse = MouseInput(0, 0, (120 * codes[0]) & 0xffffffff, 0x800, 0, 0)
            events = [event]
        else:
            events = [keyboard_event(code) for code in codes]
            events += [keyboard_event(code, True) for code in reversed(codes)]
        sent = self._send(events)
        if sent != len(events):
            # SendInput may accept only a prefix. Release any keys potentially
            # left down, even when delivery to the foreground app is blocked.
            if kind == 'keys' and sent:
                self._send([keyboard_event(code, True) for code in reversed(codes)])
            raise OSError('Windows input delivery failed. The target may be elevated or input may be blocked.')

    def close(self):
        self.closed = True
