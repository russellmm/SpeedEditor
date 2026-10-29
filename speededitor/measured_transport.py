"""Experimental transport estimates from the retained Cut / Source Tape samples.

Samples are plateau observations, not transition thresholds. Nearest-sample
selection is our approximation. Missing reverse rates are never mirrored.
"""
from collections import defaultdict
from functools import lru_cache
import json
import math
from pathlib import Path
from statistics import median


# Mode-2 one-turn trials. JOG is the mean of the two measured magnitudes;
# SCRL includes the user's overshoot correction. These are approximate.
UNITS_PER_TURN = {'JOG': 1470741, 'SCRL': 1468558}
DEFAULT_STEPS_PER_TURN = {'JOG': 60, 'SCRL': 600}  # User gains, not measured gains.
KEYBOARD_RATES = (1, 2, 4, 8, 16, 32, 64)


@lru_cache(maxsize=1)
def sample_points():
    path = Path(__file__).resolve().parent.parent / 'docs/data/shuttle-curve-2026-10-28.json'
    ledger = json.loads(path.read_text(encoding='utf-8'))
    grouped = defaultdict(list)
    for sample in ledger['samples']:
        grouped[sample['speed']].append(sample['position'])
    return tuple(sorted((median(positions), speed) for speed, positions in grouped.items()))


def speed_key(speed):
    return f'{speed:g}'


def sampled_rates():
    return tuple(speed for _, speed in sample_points() if speed)


def estimate_speed(position):
    # Compare each direction only with its own observations plus neutral.
    points = [(point, speed) for point, speed in sample_points()
              if point == 0 or point * position > 0]
    return min(points, key=lambda item: (abs(item[0] - position), abs(item[1])))[1]


def approximate_keyboard_level(speed):
    if not speed:
        return 0
    index = min(range(len(KEYBOARD_RATES)),
                key=lambda i: abs(math.log2(abs(speed) / KEYBOARD_RATES[i])))
    return (index + 1) * (1 if speed > 0 else -1)


def settings_for(profile):
    settings = {'output': 'approximate', 'stop': 'K',
                'steps_per_turn': dict(DEFAULT_STEPS_PER_TURN), 'shuttle_actions': {}}
    settings.update(profile.get('measured_transport', {}))
    return settings


def validate_settings(settings, parse_action):
    if not isinstance(settings, dict):
        raise ValueError('Measured transport settings must be an object')
    if settings.get('output', 'approximate') not in ('approximate', 'shortcuts'):
        raise ValueError('Measured output must be approximate or shortcuts')
    steps = settings.get('steps_per_turn', DEFAULT_STEPS_PER_TURN)
    if not isinstance(steps, dict) or set(steps) != set(UNITS_PER_TURN):
        raise ValueError('Measured transport needs JOG and SCRL steps per turn')
    if any(type(value) is not int or not 1 <= value <= 10000 for value in steps.values()):
        raise ValueError('Measured steps per turn must be whole numbers between 1 and 10000')
    stop = settings.get('stop', 'K')
    if parse_action(stop)[0] != 'keys':
        raise ValueError('Measured transport needs a stop keyboard shortcut')
    actions = settings.get('shuttle_actions', {})
    if not isinstance(actions, dict) or any(key not in {speed_key(rate) for rate in sampled_rates()} for key in actions):
        raise ValueError('Shuttle shortcuts must name speeds present in the sample ledger')
    for action in actions.values():
        parse_action(action)
