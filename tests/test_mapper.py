import copy
import json
import queue
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

from evdev import ecodes
from speededitor.bmd_protocol import bmd_kbd_auth
from speededitor.device import Device, parse_report
from speededitor.mapping import KEYS, Mapper, ROOT, VirtualOutput, load_profile, parse_action, save_profile, validate
from speededitor.worker import Worker
from speededitor.battery import BatteryMonitor


class ProtocolTests(unittest.TestCase):
    def test_key_report_six_slots_and_unknown_code(self):
        self.assertEqual(parse_report(bytes([4]) + struct.pack('<6H', 1, 60, 0x99, 0, 0, 0)),
                         ('keys', {1, 60, 0x99}))

    def test_signed_wheel_and_battery(self):
        self.assertEqual(parse_report(struct.pack('<BBiB', 3, 0, -1200, 255)), ('wheel', -1200))
        self.assertEqual(parse_report(bytes([7, 1, 82])), ('battery', {'charging': True, 'level': 82}))

    def test_short_and_unrecognized_reports_ignored(self):
        for data in [b'', bytes([4, 1]), bytes([3, 0]), bytes([7, 1]), bytes([99, 0])]:
            self.assertIsNone(parse_report(data))

    def test_auth_reference_vectors(self):
        # Reference outputs from the unchanged original bmd.py.
        vectors = {0: 0x3ae1206f97c10bc8, 1: 0x2b9ab32bebf244c6,
                   0xffffffffffffffff: 0x61a3f6474ff236c6,
                   0x123456789abcdef0: 0x88c756430defede8}
        for challenge, response in vectors.items():
            self.assertEqual(bmd_kbd_auth(challenge), response)

    def test_auth_exchange_and_renewal_interval(self):
        device = Device.__new__(Device)
        challenge = 0x123456789abcdef0
        device.feature_set = Mock()
        device.feature_get = Mock(side_effect=[bytes([6, 0]) + challenge.to_bytes(8, 'little'),
                                               bytes([6, 2]) + bytes(8),
                                               bytes([6, 4]) + (600).to_bytes(2, 'little') + bytes(6)])
        self.assertEqual(device.authenticate(), 570)
        response = bytes([6, 3]) + bmd_kbd_auth(challenge).to_bytes(8, 'little')
        self.assertEqual(device.feature_set.call_args_list[-1].args[0], response)

    def test_bad_auth_fails(self):
        device = Device.__new__(Device)
        device.feature_set = Mock()
        device.feature_get = Mock(return_value=bytes(10))
        with self.assertRaises(RuntimeError):
            device.authenticate()

    def test_battery_feature_query_reports_not_charging(self):
        device = Device.__new__(Device)
        device.feature_get = Mock(return_value=bytes([7, 0, 47]))
        self.assertEqual(device.battery_status(), {'charging': False, 'level': 47})
        device.feature_get.assert_called_once_with(7, 3)

    def test_invalid_battery_values_are_rejected(self):
        device = Device.__new__(Device)
        for data in [bytes([7, 1, 255]), bytes([7, 2, 50]), bytes([4, 0, 50])]:
            device.feature_get = Mock(return_value=data)
            with self.assertRaises(ValueError):
                device.battery_status()


class BatteryMonitorTests(unittest.TestCase):
    @patch('speededitor.battery.discover', return_value=[{'path': '/dev/fake', 'accessible': True}])
    @patch('speededitor.battery.Device')
    def test_passive_query_does_not_authenticate_or_change_leds(self, device, discover):
        device.return_value.battery_status.return_value = {'level': 42, 'charging': True}
        monitor = BatteryMonitor(queue.Queue())
        self.assertEqual(monitor.check(), ('battery', {'level': 42, 'charging': True}))
        device.return_value.authenticate.assert_not_called()
        device.return_value.write.assert_not_called()
        device.return_value.close.assert_called_once_with(clear_leds=False)

    @patch('speededitor.battery.discover', side_effect=[[], [{'path': '/dev/fake', 'accessible': True}]])
    @patch('speededitor.battery.Device')
    def test_unplug_and_reconnect_update_the_status(self, device, discover):
        device.return_value.battery_status.return_value = {'level': 43, 'charging': False}
        monitor = BatteryMonitor(queue.Queue())
        self.assertEqual(monitor.check(), ('battery_unavailable', 'Battery: disconnected'))
        self.assertEqual(monitor.check(), ('battery', {'level': 43, 'charging': False}))

    @patch('speededitor.battery.discover', return_value=[{'path': '/dev/fake', 'accessible': True}])
    @patch('speededitor.battery.Device')
    def test_failed_query_clears_stale_battery_and_closes_handle(self, device, discover):
        device.return_value.battery_status.side_effect = OSError('unplugged')
        monitor = BatteryMonitor(queue.Queue())
        self.assertEqual(monitor.check(), ('battery_unavailable', 'Battery: unavailable'))
        device.return_value.close.assert_called_once_with(clear_leds=False)


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile(ROOT / 'profiles/desktop.json')
        self.emitted = []
        self.mapper = Mapper(self.profile, self.emitted.append)

    def test_all_profiles_cover_every_button(self):
        self.assertEqual(len(KEYS), 43)
        for path in (ROOT / 'profiles').glob('*.json'):
            self.assertEqual(set(load_profile(path)['buttons']), set(KEYS.values()))

    def test_press_edges_no_repeat_and_release(self):
        self.mapper.buttons({1})
        self.mapper.buttons({1})
        self.mapper.buttons({1, 2})
        self.mapper.buttons(set())
        self.mapper.buttons({1})
        self.assertEqual(self.emitted, ['Ctrl+N', 'Ctrl+Shift+N', 'Ctrl+N'])

    def test_unknown_button_does_not_crash_or_emit(self):
        self.assertEqual(self.mapper.buttons({0xffff}), [('UNKNOWN_FFFF', '')])
        self.assertEqual(self.emitted, [])

    def test_fractional_wheel_accumulates_and_reverse_is_immediate(self):
        self.assertEqual(self.mapper.wheel(360)[1], 0)
        self.assertEqual(self.mapper.wheel(360), ('ScrollDown', 1))
        self.mapper.wheel(360)
        self.assertEqual(self.mapper.wheel(-720), ('ScrollUp', 1))

    def test_modes_reset_wheel_remainder(self):
        self.mapper.wheel(100)
        self.mapper.buttons({0x1c})  # SHTL
        self.assertEqual(self.mapper.mode, 'SHTL')
        self.assertEqual(self.mapper.remainder, 0)
        self.assertEqual(self.mapper.wheel(2160), ('VolumeUp', 1))

    def test_corrupt_wheel_does_not_flood_output(self):
        self.mapper.wheel(2147483647)
        self.assertEqual(len(self.emitted), 20)
        self.assertLess(self.mapper.remainder, 720)

    def test_invalid_actions_and_profiles_rejected(self):
        for action in ['Ctrl+NoSuchKey', 'Ctrl+', 'Ctrl+Ctrl', 42]:
            with self.assertRaises(ValueError):
                parse_action(action)
        for threshold in [0, -1, True, 1.5, 99999]:
            profile = copy.deepcopy(self.profile)
            profile['wheel']['JOG']['threshold'] = threshold
            with self.assertRaises(ValueError):
                validate(profile)

    def test_malformed_profile_shapes_rejected(self):
        for value in [[], None, 1, {'version': True, 'name': 'bad'},
                      {**self.profile, 'buttons': []}, {**self.profile, 'wheel': []},
                      {**self.profile, 'wheel': {'JOG': None}}]:
            with self.assertRaises(ValueError):
                validate(value)

    def test_keyboard_chord_and_scroll_parsing(self):
        self.assertEqual(parse_action('Ctrl+Shift+S'), ('keys', [ecodes.KEY_LEFTCTRL, ecodes.KEY_LEFTSHIFT, ecodes.KEY_S]))
        self.assertEqual(parse_action(''), ('none', []))
        self.assertEqual(parse_action('ScrollUp'), ('scroll', [1]))

    def test_save_rejects_invalid_without_changing_existing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'profile.json'
            save_profile(path, self.profile)
            original = path.read_text()
            bad = copy.deepcopy(self.profile)
            bad['buttons']['CAM1'] = 'NotAKey'
            with self.assertRaises(ValueError):
                save_profile(path, bad)
            self.assertEqual(path.read_text(), original)
            self.assertEqual(load_profile(path), self.profile)

    def test_keyboard_released_in_reverse_order(self):
        output = VirtualOutput.__new__(VirtualOutput)
        output.device = Mock()
        output.emit('Ctrl+C')
        self.assertEqual([c.args for c in output.device.write.call_args_list],
                         [(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1), (ecodes.EV_KEY, ecodes.KEY_C, 1),
                          (ecodes.EV_KEY, ecodes.KEY_C, 0), (ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0)])


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile(ROOT / 'profiles/desktop.json')

    @patch('speededitor.worker.resolve_running', return_value=True)
    @patch('speededitor.worker.Device')
    def test_resolve_running_does_not_open_device(self, device, resolve):
        worker = Worker()
        worker.run(self.profile, True)
        device.assert_not_called()
        self.assertEqual(worker.events.get()[0], 'error')
        self.assertEqual(worker.events.get()[0], 'stopped')

    @patch('speededitor.worker.resolve_running', return_value=False)
    @patch('speededitor.worker.discover', return_value=[{'path': '/dev/fake', 'accessible': True}])
    @patch('speededitor.worker.Device')
    @patch('speededitor.worker.VirtualOutput')
    def test_monitor_sends_no_keyboard_events_and_disconnect_closes_device(self, output, device, discover, resolve):
        device.return_value.authenticate.return_value = 570
        device.return_value.read.side_effect = [bytes([4]) + struct.pack('<6H', 1, 0, 0, 0, 0, 0), OSError('unplugged')]
        worker = Worker()
        worker.run(self.profile, False)
        output.assert_not_called()
        device.return_value.close.assert_called_once()
        events = list(worker.events.queue)
        self.assertIn('keys', [kind for kind, data in events])
        self.assertEqual(events[-1][0], 'stopped')

    @patch('speededitor.worker.resolve_running', return_value=False)
    @patch('speededitor.worker.discover', return_value=[{'path': '/dev/fake', 'accessible': True}])
    @patch('speededitor.worker.Device')
    @patch('speededitor.worker.VirtualOutput')
    def test_mapping_emits_and_closes_virtual_device(self, output, device, discover, resolve):
        device.return_value.authenticate.return_value = 570
        device.return_value.read.side_effect = [bytes([4]) + struct.pack('<6H', 1, 0, 0, 0, 0, 0), OSError('unplugged')]
        worker = Worker()
        worker.run(self.profile, True)
        output.return_value.emit.assert_called_once_with('Ctrl+N')
        output.return_value.close.assert_called_once()
        device.return_value.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
