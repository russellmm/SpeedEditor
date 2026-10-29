from copy import deepcopy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

from speededitor.device import LinuxDevice, parse_report
from speededitor.mapping import Mapper, ROOT, load_profile, save_profile, validate
from speededitor.measured_transport import (UNITS_PER_TURN, estimate_speed,
                                            sampled_rates, settings_for)
from speededitor.worker import Worker


def measured_profile():
    profile = load_profile(ROOT / 'profiles/desktop.json')
    for settings in profile['wheel'].values():
        settings['behavior'] = 'measured'
    return profile


def keys(*codes):
    return bytes([4]) + struct.pack('<6H', *(list(codes) + [0] * (6 - len(codes))))


def wheel(mode, position):
    return struct.pack('<BBiB', 3, mode, position, 255) + bytes(6)


class MeasuredTransportTests(unittest.TestCase):
    def setUp(self):
        self.profile = measured_profile()
        self.actions = []
        self.mapper = Mapper(self.profile, self.actions.append)

    def test_every_ledger_sample_selects_its_reported_rate(self):
        ledger = json.loads((ROOT / 'docs/data/shuttle-curve-2026-10-28.json').read_text())
        for sample in ledger['samples']:
            with self.subTest(position=sample['position']):
                self.assertEqual(estimate_speed(sample['position']), sample['speed'])
        self.assertNotIn(-2, sampled_rates())
        self.assertNotIn(-32, sampled_rates())
        self.assertEqual(estimate_speed(0), 0)

    def test_measured_mode_is_opt_in_and_legacy_custom_profiles_are_preserved(self):
        standard = load_profile(ROOT / 'profiles/desktop.json')
        original = deepcopy(standard)
        mapper = Mapper(standard)
        self.assertEqual(mapper.hardware_mode, 0)
        self.assertEqual(standard, original)
        del standard['wheel']['JOG']['behavior']
        standard['wheel']['JOG'].update(left='VolumeDown', right='VolumeUp')
        actions = []
        mapper = Mapper(standard, actions.append)
        mapper.wheel(360)
        self.assertEqual(actions, ['VolumeUp'])
        self.assertEqual(mapper.hardware_mode, 0)

    def test_measured_calibration_produces_user_selected_steps_per_turn(self):
        self.mapper.wheel(UNITS_PER_TURN['JOG'] // 2)
        self.mapper.wheel(UNITS_PER_TURN['JOG'] - UNITS_PER_TURN['JOG'] // 2)
        self.assertEqual(self.actions.count('Right'), 60)
        self.assertEqual(self.mapper.remainder, 0)
        self.mapper.buttons({0x1e})
        self.profile['measured_transport'] = settings_for(self.profile)
        self.profile['measured_transport']['steps_per_turn']['SCRL'] = 40
        mapper = Mapper(self.profile, self.actions.append)
        mapper.buttons({0x1e})
        mapper.wheel(-UNITS_PER_TURN['SCRL'])
        self.assertEqual(self.actions.count('Left'), 40)

    def test_relative_reversal_discards_residue_and_large_reports_are_bounded(self):
        self.mapper.wheel(10000)
        self.mapper.wheel(-24513)
        self.assertEqual(self.actions, ['K', 'Left'])
        self.actions.clear()
        self.mapper.wheel(2**31 - 1)
        self.assertEqual(self.actions, ['K'] + ['Right'] * 80)
        self.mapper.wheel(0)
        self.assertEqual(len(self.actions), 81)

    def test_shuttle_is_absolute_and_keyboard_approximation_is_visible(self):
        self.mapper.buttons({0x1c})
        message, count = self.mapper.wheel(305)
        self.assertEqual(self.mapper.shuttle_level, 0.25)
        self.assertIn('approximate', message)
        self.assertEqual(self.actions, ['K', 'L'])
        self.mapper.wheel(305)
        self.mapper.wheel(321)
        self.assertEqual(self.actions, ['K', 'L'])
        self.mapper.wheel(401)
        self.assertEqual(self.mapper.shuttle_level, 0.5)
        self.assertEqual(self.actions, ['K', 'L'])  # Same output level; no playback interruption.
        self.mapper.wheel(4096)
        self.assertEqual(self.mapper.shuttle_level, 64)
        self.assertEqual(self.actions[-8:], ['K'] + ['L'] * 7)
        self.mapper.wheel(-4096)
        self.assertEqual(self.mapper.shuttle_level, -64)
        self.assertEqual(self.actions[-8:], ['K'] + ['J'] * 7)
        self.mapper.wheel(0)
        self.assertEqual(self.actions[-1], 'K')

    def test_repeated_shtl_stops_retains_neutral_and_resumes_forward_on_return(self):
        self.mapper.buttons({0x1c})
        self.mapper.buttons(set())
        self.mapper.wheel(2023)
        self.mapper.buttons({0x1c})
        self.assertEqual(self.actions[-1], 'K')
        self.assertEqual(self.mapper.shuttle_position, 2023)
        count = len(self.actions)
        self.mapper.wheel(2023)
        self.assertEqual(len(self.actions), count)
        self.assertEqual(self.mapper.shuttle_level, 0)
        self.mapper.wheel(1782)
        self.assertEqual(self.mapper.shuttle_level, 3)
        self.assertEqual(self.actions[-1], 'L')
        self.mapper.buttons({0x1d})
        self.mapper.buttons({0x1c})
        self.assertIsNone(self.mapper.measured_position)
        self.assertEqual(self.mapper.shuttle_position, 0)
        self.assertEqual(self.mapper.hardware_mode, 3)
        self.mapper.wheel(0)
        self.assertEqual(self.mapper.shuttle_level, 0)

    def test_stop_play_stops_without_restarting_on_stationary_absolute_report(self):
        self.mapper.buttons({0x1c})
        self.mapper.wheel(1301)
        self.mapper.buttons({0x3c})
        count = len(self.actions)
        self.mapper.wheel(1301)
        self.assertEqual(len(self.actions), count)
        self.assertNotIn('Space', self.actions)

    def test_direct_speed_shortcuts_and_unassigned_rates_stop_playback(self):
        config = settings_for(self.profile)
        config.update(output='shortcuts', stop='Ctrl+K',
                      shuttle_actions={'0.25': 'Ctrl+,', '-0.25': 'Ctrl+Shift+,'})
        self.profile['measured_transport'] = config
        mapper = Mapper(self.profile, self.actions.append)
        mapper.buttons({0x1c})
        mapper.wheel(305)
        self.assertEqual(self.actions, ['Ctrl+K', 'Ctrl+,'])
        mapper.wheel(310)
        self.assertEqual(len(self.actions), 2)
        message, _ = mapper.wheel(401)
        self.assertIn('unassigned; stopped', message)
        self.assertEqual(self.actions[-1], 'Ctrl+K')
        mapper.wheel(-337)
        self.assertEqual(self.actions[-2:], ['Ctrl+K', 'Ctrl+Shift+,'])
        mapper.stop()
        self.assertEqual(self.actions[-1], 'Ctrl+K')

    def test_out_of_range_absolute_reports_are_ignored(self):
        self.mapper.buttons({0x1c})
        self.mapper.wheel(2**31 - 1)
        self.assertEqual(self.actions, [])
        self.assertIsNone(self.mapper.measured_position)

    def test_measured_configuration_round_trips_and_invalid_settings_are_rejected(self):
        self.profile['measured_transport'] = settings_for(self.profile)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'profile.json'
            save_profile(path, self.profile)
            self.assertEqual(load_profile(path), self.profile)
        for changes in [{'output': 'native'}, {'stop': ''}, {'stop': 'ScrollDown'},
                        {'shuttle_actions': {'-32': 'J'}}, {'shuttle_actions': {'1': 42}},
                        {'steps_per_turn': {'JOG': True, 'SCRL': 10}},
                        {'steps_per_turn': {'JOG': 0, 'SCRL': 10}}]:
            profile = deepcopy(self.profile)
            profile['measured_transport'].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate(profile)

    def test_hardware_reports_select_observed_modes_and_filter_stale_reports(self):
        device = LinuxDevice.__new__(LinuxDevice)
        device.write = Mock()
        device.configure_wheel('JOG', 2)
        device.configure_wheel('SHTL', 3)
        self.assertEqual([call.args[0] for call in device.write.call_args_list],
                         [bytes.fromhex('030200000000ff'), bytes([4, 1]),
                          bytes.fromhex('030300000000ff'), bytes([4, 2])])
        self.assertIsNone(parse_report(wheel(2, 305), wheel_mode=3))
        self.assertEqual(parse_report(wheel(3, 305), wheel_mode=3), ('wheel', 305))

    def run_worker(self, active):
        worker = Worker()
        with patch('speededitor.worker.resolve_running', return_value=False), \
                patch('speededitor.worker.discover', return_value=[{'path': 'fake', 'accessible': True}]), \
                patch('speededitor.worker.Device') as device, \
                patch('speededitor.worker.VirtualOutput') as output:
            device.return_value.authenticate.return_value = 570
            device.return_value.read.side_effect = [keys(0x1c), keys(), wheel(2, 4096), wheel(3, 305),
                                                    keys(0x1c), wheel(3, 305), keys(0x1d),
                                                    wheel(3, 4096), OSError('disconnected')]
            worker.run(self.profile, active)
            return worker, device, output

    def test_worker_configures_measured_modes_without_resetting_repeated_shtl(self):
        worker, device, output = self.run_worker(True)
        self.assertEqual([call.args for call in device.return_value.configure_wheel.call_args_list],
                         [('JOG', 2), ('SHTL', 3), ('JOG', 2)])
        self.assertEqual([call.args[0] for call in output.return_value.emit.call_args_list], ['K', 'L', 'K'])
        output.return_value.close.assert_called_once()
        device.return_value.close.assert_called_once()

    def test_monitor_measures_without_creating_keyboard_output(self):
        worker, device, output = self.run_worker(False)
        output.assert_not_called()
        events = list(worker.events.queue)
        self.assertTrue(any(kind == 'wheel' and 'Measured target +0.25' in data[1] for kind, data in events))
        self.assertEqual(events[-1][0], 'stopped')

    def test_profile_update_switches_hardware_mode_and_ignores_old_absolute_input(self):
        worker = Worker()
        updated = deepcopy(self.profile)
        updated['wheel']['SHTL']['behavior'] = 'standard'
        packets = iter([keys(0x1c), wheel(3, 1301), wheel(3, 4096), wheel(0, 2160)])

        def read():
            packet = next(packets, None)
            if packet is None:
                raise OSError('disconnected')
            if packet == wheel(3, 1301):
                worker.update(updated)
            return packet

        with patch('speededitor.worker.resolve_running', return_value=False), \
                patch('speededitor.worker.discover', return_value=[{'path': 'fake', 'accessible': True}]), \
                patch('speededitor.worker.Device') as device, \
                patch('speededitor.worker.VirtualOutput') as output:
            device.return_value.authenticate.return_value = 570
            device.return_value.read.side_effect = read
            worker.run(self.profile, True)
            device.return_value.relative_wheel.assert_called_once_with('SHTL')
            self.assertEqual([call.args[0] for call in output.return_value.emit.call_args_list],
                             ['K', 'L', 'K', 'K', 'L', 'K'])
