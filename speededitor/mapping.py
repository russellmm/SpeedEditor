"""Validated profiles and tap-on-press keyboard/scroll output."""
from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import os

from evdev import UInput, ecodes
from .bmd_protocol import SpeedEditorKey

ROOT = Path(__file__).resolve().parent.parent
KEYS = {key.value: key.name for key in SpeedEditorKey if key.value}
MODES = ('JOG', 'SCRL', 'SHTL')
ALIASES = {'CTRL': 'LEFTCTRL', 'CONTROL': 'LEFTCTRL', 'SHIFT': 'LEFTSHIFT',
           'ALT': 'LEFTALT', 'SUPER': 'LEFTMETA', 'META': 'LEFTMETA',
           'ESCAPE': 'ESC', 'RETURN': 'ENTER', 'PGUP': 'PAGEUP',
           'PGDN': 'PAGEDOWN', 'PLUS': 'EQUAL', 'VOLUMEUP': 'VOLUMEUP',
           'VOLUMEDOWN': 'VOLUMEDOWN', 'PLAYPAUSE': 'PLAYPAUSE'}


def parse_action(action):
    if not isinstance(action, str):
        raise ValueError('Shortcut must be text')
    action = action.strip()
    if not action or action == 'None':
        return 'none', []
    if action in ('ScrollUp', 'ScrollDown'):
        return 'scroll', [1 if action == 'ScrollUp' else -1]
    parts = [part.strip().upper() for part in action.split('+')]
    codes = []
    for part in parts:
        name = ALIASES.get(part, part)
        name = name if name.startswith('KEY_') else 'KEY_' + name
        code = ecodes.ecodes.get(name)
        if code is None:
            raise ValueError(f'Unknown key: {part or "(empty)"}. Example: Ctrl+Shift+S')
        if code in codes:
            raise ValueError('A shortcut cannot contain the same key twice')
        codes.append(code)
    if len(codes) > 6:
        raise ValueError('Use at most six keys in one shortcut')
    return 'keys', codes


def validate(profile):
    if not isinstance(profile, dict) or type(profile.get('version')) is not int or profile['version'] != 1 or not isinstance(profile.get('name'), str):
        raise ValueError('Unsupported profile format')
    if not isinstance(profile.get('buttons'), dict) or set(profile['buttons']) != set(KEYS.values()):
        raise ValueError('Profile must contain all 43 Speed Editor buttons')
    for action in profile['buttons'].values():
        parse_action(action)
    if not isinstance(profile.get('wheel'), dict):
        raise ValueError('Profile must contain three wheel maps')
    for mode in MODES:
        if not isinstance(profile['wheel'].get(mode), dict) or not all(key in profile['wheel'][mode] for key in ('threshold', 'left', 'right')):
            raise ValueError(f'Incomplete wheel map: {mode}')
        wheel = profile['wheel'][mode]
        threshold = wheel['threshold']
        if isinstance(threshold, bool) or not isinstance(threshold, int) or not 1 <= threshold <= 8192:
            raise ValueError('Wheel threshold must be an integer between 1 and 8192')
        for direction in ('left', 'right'):
            parse_action(wheel[direction])
    return profile


def load_profile(path):
    return validate(json.loads(Path(path).read_text()))


def save_profile(path, profile):
    validate(profile)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement keeps the last good map intact if saving is interrupted.
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as tmp:
        temporary = Path(tmp.name)
        try:
            json.dump(profile, tmp, indent=2)
            tmp.write('\n')
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


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


class Mapper:
    def __init__(self, profile, emit=lambda action: None):
        self.profile = deepcopy(validate(profile))
        self.emit = emit
        self.held = set()
        self.mode = 'JOG'
        self.remainder = 0

    def buttons(self, current):
        pressed = sorted(current - self.held)
        self.held = set(current)
        events = []
        for key in pressed:
            name = KEYS.get(key, f'UNKNOWN_{key:04X}')
            if name in MODES:
                self.mode = name
                self.remainder = 0
            action = self.profile['buttons'].get(name, '')
            if action:
                self.emit(action)
            events.append((name, action))
        return events

    def wheel(self, delta):
        settings = self.profile['wheel'][self.mode]
        # Reverse direction immediately; discard residual motion from the other direction.
        if delta * self.remainder < 0:
            self.remainder = 0
        self.remainder += delta
        steps = math.trunc(self.remainder / settings['threshold'])
        self.remainder -= steps * settings['threshold']
        action = settings['right' if steps > 0 else 'left']
        # Bound output for a single corrupt/large report; do not queue extra actions.
        count = min(abs(steps), 20)
        for _ in range(count):
            if action:
                self.emit(action)
        return action, count
