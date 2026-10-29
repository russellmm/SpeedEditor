"""Platform keyboard backends; importing or constructing sends no shortcuts."""
import os

if os.name == 'nt':
    from .windows_output import KEY_CODES, WindowsOutput as VirtualOutput

    def key_code(name):
        return KEY_CODES.get(name)
else:
    from evdev import UInput, ecodes

    def key_code(name):
        return ecodes.ecodes.get(name)

    class VirtualOutput:
        def __init__(self):
            keyboard_codes = sorted({value for name, value in ecodes.ecodes.items()
                                     if name.startswith('KEY_') and name not in
                                     ('KEY_MAX', 'KEY_CNT', 'KEY_MIN_INTERESTING')})
            self.device = UInput({ecodes.EV_KEY: keyboard_codes,
                                  ecodes.EV_REL: [ecodes.REL_WHEEL]},
                                 name='SpeedEditor Virtual Keyboard',
                                 vendor=0x1edb, product=0x0001)

        def emit(self, action):
            from .mapping import parse_action
            kind, codes = parse_action(action)
            if kind == 'scroll':
                self.device.write(ecodes.EV_REL, ecodes.REL_WHEEL, codes[0])
                self.device.syn()
            elif kind == 'keys':
                pressed = []
                try:
                    for code in codes:
                        self.device.write(ecodes.EV_KEY, code, 1)
                        pressed.append(code)
                    self.device.syn()
                finally:
                    for code in reversed(pressed):
                        self.device.write(ecodes.EV_KEY, code, 0)
                    self.device.syn()

        def close(self):
            self.device.close()
