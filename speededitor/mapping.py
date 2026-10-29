"""Validated profiles and tap-on-press keyboard/scroll output."""
from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import os

from .output import VirtualOutput, key_code
from .bmd_protocol import SpeedEditorKey
from .measured_transport import (UNITS_PER_TURN, KEYBOARD_RATES, approximate_keyboard_level,
                                 estimate_speed, settings_for, speed_key, validate_settings)

ROOT = Path(__file__).resolve().parent.parent
KEYS = {key.value: key.name for key in SpeedEditorKey if key.value}
MODES = ('JOG', 'SCRL', 'SHTL')
ALIASES = {'CTRL': 'LEFTCTRL', 'CONTROL': 'LEFTCTRL', 'SHIFT': 'LEFTSHIFT',
           'ALT': 'LEFTALT', 'SUPER': 'LEFTMETA', 'META': 'LEFTMETA',
           'ESCAPE': 'ESC', 'RETURN': 'ENTER', 'PGUP': 'PAGEUP',
           'PGDN': 'PAGEDOWN', 'PLUS': 'EQUAL', 'VOLUMEUP': 'VOLUMEUP',
           'VOLUMEDOWN': 'VOLUMEDOWN', 'PLAYPAUSE': 'PLAYPAUSE'}
ALIASES.update({',': 'COMMA', '.': 'DOT', '/': 'SLASH', ';': 'SEMICOLON',
                "'": 'APOSTROPHE', '[': 'LEFTBRACE', ']': 'RIGHTBRACE',
                '\\': 'BACKSLASH', '`': 'GRAVE', '-': 'MINUS', '=': 'EQUAL',
                'PERIOD': 'DOT', 'EQUALS': 'EQUAL', 'QUOTE': 'APOSTROPHE',
                'LEFTBRACKET': 'LEFTBRACE', 'RIGHTBRACKET': 'RIGHTBRACE',
                'BACKTICK': 'GRAVE', 'WIN': 'LEFTMETA', 'WINDOWS': 'LEFTMETA',
                'PRINTSCREEN': 'SYSRQ'})


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
        code = key_code(name)
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
    overrides = profile.get('resolve_buttons', {})
    if not isinstance(overrides, dict) or any(name not in KEYS.values() or name in MODES for name in overrides):
        raise ValueError('Resolve overrides must name known buttons; JOG, SCRL and SHTL stay native')
    for action in overrides.values():
        parse_action(action)
    if not isinstance(profile.get('wheel'), dict):
        raise ValueError('Profile must contain three wheel maps')
    for mode in MODES:
        if not isinstance(profile['wheel'].get(mode), dict) or not all(key in profile['wheel'][mode] for key in ('threshold', 'left', 'right')):
            raise ValueError(f'Incomplete wheel map: {mode}')
        wheel = profile['wheel'][mode]
        if wheel.get('behavior', 'custom') not in ('standard', 'custom', 'measured'):
            raise ValueError('Wheel behavior must be standard, custom or measured')
        threshold = wheel['threshold']
        if isinstance(threshold, bool) or not isinstance(threshold, int) or not 1 <= threshold <= 8192:
            raise ValueError('Wheel threshold must be an integer between 1 and 8192')
        for direction in ('left', 'right'):
            parse_action(wheel[direction])
    validate_settings(profile.get('measured_transport', {}), parse_action)
    return profile


def load_profile(path):
    return validate(json.loads(Path(path).read_text(encoding='utf-8')))


def save_profile(path, profile):
    validate(profile)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement keeps the last good map intact if saving is interrupted.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as tmp:
            temporary = Path(tmp.name)
            json.dump(profile, tmp, indent=2)
            tmp.write('\n')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class Mapper:
    def __init__(self, profile, emit=lambda action: None):
        self.profile = deepcopy(validate(profile))
        self.emit = emit
        self.held = set()
        self.mode = 'JOG'
        self.remainder = 0
        self.shuttle_position = 0
        self.shuttle_level = 0
        self.measured = settings_for(self.profile)
        self.measured_position = None
        self.measured_output_level = 0

    @property
    def hardware_mode(self):
        if self.profile['wheel'][self.mode].get('behavior') == 'measured':
            return 3 if self.mode == 'SHTL' else 2
        return 0

    def stop(self, reset_position=True):
        if self.shuttle_level:
            self.emit(self.measured['stop'] if self.hardware_mode == 3 else 'K')
        if reset_position:
            self.shuttle_position = 0
            self.measured_position = None
        self.shuttle_level = 0
        self.measured_output_level = 0
        self.remainder = 0

    def buttons(self, current):
        pressed = sorted(current - self.held)
        self.held = set(current)
        events = []
        for key in pressed:
            name = KEYS.get(key, f'UNKNOWN_{key:04X}')
            shuttle_was_playing = bool(self.shuttle_level)
            if name in MODES:
                # Re-pressing measured SHTL stops playback without moving its
                # neutral. Only leaving and re-entering resets hardware mode 3.
                self.stop(reset_position=not (name == self.mode == 'SHTL' and self.hardware_mode == 3))
                self.mode = name
            elif name == 'STOP_PLAY':
                self.stop(reset_position=self.hardware_mode != 3)
            action = self.profile['buttons'].get(name, '')
            # The default transport button stops a latched shuttle. Do not
            # immediately restart playback by toggling Space after stopping it.
            stopped_shuttle = (name == 'STOP_PLAY' and shuttle_was_playing
                               and action in ('Space', 'PlayPause'))
            if action and not stopped_shuttle:
                self.emit(action)
            stop_action = self.measured['stop'] if self.hardware_mode == 3 else 'K'
            events.append((name, stop_action if stopped_shuttle else action))
        return events

    def wheel(self, delta):
        settings = self.profile['wheel'][self.mode]
        if settings.get('behavior') == 'measured':
            return self.measured_shuttle(delta) if self.mode == 'SHTL' else self.measured_steps(delta, settings)
        standard = settings.get('behavior', 'custom') == 'standard'
        if standard and self.mode == 'SHTL':
            return self.shuttle(delta, settings['threshold'])
        # Reverse direction immediately; discard residual motion from the other direction.
        if delta * self.remainder < 0:
            self.remainder = 0
        self.remainder += delta
        steps = math.trunc(self.remainder / settings['threshold'])
        self.remainder -= steps * settings['threshold']
        action = ('Right' if steps > 0 else 'Left') if standard else settings['right' if steps > 0 else 'left']
        # Bound output for a single corrupt/large report; do not queue extra actions.
        gain = 10 if standard and self.mode == 'SCRL' else 1
        count = min(abs(steps) * gain, 80 if standard else 20)
        if standard and count:
            # Stop normal playback before stepping; no timer or queued repeat
            # continues after physical wheel reports stop arriving.
            self.emit('K')
        for _ in range(count):
            if action:
                self.emit(action)
        return action, count

    def measured_steps(self, delta, settings):
        # Mode 2 has a measured angular scale. Frame/seek gain is user chosen.
        if delta * self.remainder < 0:
            self.remainder = 0
        self.remainder += delta * self.measured['steps_per_turn'][self.mode]
        unit = UNITS_PER_TURN[self.mode]
        steps = math.trunc(self.remainder / unit)
        self.remainder -= steps * unit
        count = min(abs(steps), 80)
        action = settings['right' if steps > 0 else 'left']
        if count and action:
            self.emit(self.measured['stop'])
            for _ in range(count):
                self.emit(action)
        return action, count

    def measured_shuttle(self, position):
        # Mode 3 reports absolute displacement, never a relative delta.
        if abs(position) > 4096:
            return 'Measured position outside captured range', 0
        if position == self.measured_position:
            return 'Measured unchanged', 0
        self.measured_position = position
        self.shuttle_position = position
        speed = estimate_speed(position)
        if speed == self.shuttle_level:
            return 'Measured unchanged', 0
        self.shuttle_level = speed
        if self.measured['output'] == 'shortcuts':
            self.emit(self.measured['stop'])
            action = self.measured['shuttle_actions'].get(speed_key(speed), '') if speed else ''
            action = action.strip()
            if action == 'None':
                action = ''
            if action:
                self.emit(action)
            detail = action or ('stopped' if not speed else 'unassigned; stopped')
            return f'Measured target {speed:+g}× → {detail}', 1 + bool(action)
        level = approximate_keyboard_level(speed)
        detail = 'stopped' if not level else f'approximate J/K/L level {abs(level)} (nominal {KEYBOARD_RATES[abs(level) - 1]}×)'
        if level == self.measured_output_level:
            return f'Measured target {speed:+g}× → {detail}', 0
        self.emit(self.measured['stop'])
        self.measured_output_level = level
        for _ in range(abs(level)):
            self.emit('L' if level > 0 else 'J')
        return f'Measured target {speed:+g}× → {detail}', 1 + abs(level)

    def shuttle(self, delta, threshold):
        # Integrate relative motion into displacement from the SHTL entry point.
        # Playback is latched: an idle wheel does not stop it. Returning to
        # neutral, STOP/PLAY, a mode change or stopping the mapper does.
        limit = 4 * threshold
        self.shuttle_position = max(-limit, min(limit, self.shuttle_position + delta))
        magnitude = min(4, abs(self.shuttle_position) // threshold)
        level = magnitude * (1 if self.shuttle_position > 0 else -1)
        if level == self.shuttle_level:
            return 'Shuttle unchanged', 0
        self.emit('K')
        self.shuttle_level = level
        if level:
            action = 'L' if level > 0 else 'J'
            for _ in range(abs(level)):
                self.emit(action)
            return f'Shuttle {"forward" if level > 0 else "reverse"} level {abs(level)}', abs(level)
        return 'Shuttle stopped', 1
