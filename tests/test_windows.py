"""Windows adapter tests mock all output; no keyboard events reach the desktop."""
import ctypes
import os
import queue
import sys
import unittest
from unittest.mock import Mock, patch

from speededitor.windows_hid import WindowsDevice


class WindowsHidTests(unittest.TestCase):
    def setUp(self):
        self.hid = Mock()
        self.patch = patch.dict(sys.modules, {'hid': self.hid})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.device = WindowsDevice(b'fake-hid-path')
        self.handle = self.hid.device.return_value

    def test_battery_close_sends_no_led_clear(self):
        self.device.close(clear_leds=False)
        self.handle.write.assert_not_called()
        self.handle.close.assert_called_once()
        self.device.close(clear_leds=False)
        self.handle.close.assert_called_once()

    def test_short_feature_and_output_reports_fail(self):
        self.handle.get_feature_report.return_value = [6, 0]
        with self.assertRaises(OSError):
            self.device.feature_get(6, 10)
        self.handle.send_feature_report.return_value = 2
        with self.assertRaises(OSError):
            self.device.feature_set(bytes(10))
        self.handle.write.return_value = 1
        with self.assertRaises(OSError):
            self.device.write(bytes([4, 1]))

    def test_timed_reads_and_close_on_open_failure(self):
        self.handle.read.return_value = [3, 0]
        self.assertEqual(self.device.read(.1), bytes([3, 0]))
        self.handle.read.assert_called_once_with(64, 100)
        self.handle.open_path.side_effect = OSError('busy')
        with self.assertRaises(OSError):
            WindowsDevice(b'fake-hid-path')
        self.handle.close.assert_called_once()

    @patch('speededitor.windows_hid.interface_paths', return_value=[b'BUSY', b'accessible'])
    def test_busy_interfaces_remain_visible_and_are_deduplicated(self, paths):
        from speededitor.windows_hid import discover
        self.hid.enumerate.return_value = [{'path': b'ACCESSIBLE', 'product_string': 'Speed Editor'}]
        devices = discover()
        self.assertEqual(len(devices), 2)
        self.assertTrue(devices[0]['accessible'])
        self.assertFalse(devices[1]['accessible'])


@unittest.skipUnless(os.name == 'nt', 'Windows SendInput ABI')
class WindowsLockTests(unittest.TestCase):
    def test_only_one_adapter_lock_can_exist(self):
        from speededitor.windows_hid import ResolveBridgeLock
        first = ResolveBridgeLock(os.getpid())
        try:
            with self.assertRaises(RuntimeError):
                ResolveBridgeLock(os.getpid())
        finally:
            first.close()
        another = ResolveBridgeLock(os.getpid())
        another.close()


@unittest.skipUnless(os.name == 'nt', 'Windows SendInput ABI')
class WindowsOutputTests(unittest.TestCase):
    def setUp(self):
        from speededitor.windows_output import WindowsOutput
        self.library = Mock()
        patcher = patch('speededitor.windows_output.c.WinDLL', return_value=self.library)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.output = WindowsOutput()
        self.library.SendInput.assert_not_called()

    def test_input_abi_matches_windows(self):
        from speededitor.windows_output import Input
        self.assertEqual(ctypes.sizeof(Input), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)

    def test_chord_releases_in_reverse_order(self):
        events = []
        def send(count, data, size):
            events.extend((data[i].keyboard.vk, data[i].keyboard.flags) for i in range(count))
            return count
        self.library.SendInput.side_effect = send
        self.output.emit('Ctrl+Shift+C')
        self.assertEqual(events, [(0xa2, 0), (0xa0, 0), (ord('C'), 0),
                                  (ord('C'), 2), (0xa0, 2), (0xa2, 2)])

    def test_scroll_and_navigation_extended_flags(self):
        events = []
        def send(count, data, size):
            for i in range(count):
                events.append((data[i].type, data[i].mouse.data if data[i].type == 0
                               else data[i].keyboard.flags))
            return count
        self.library.SendInput.side_effect = send
        self.output.emit('ScrollDown')
        self.output.emit('Right')
        self.assertEqual(events, [(0, (-120) & 0xffffffff), (1, 1), (1, 3)])

    def test_partial_send_releases_keys_and_fails(self):
        self.library.SendInput.side_effect = [1, 2]
        with self.assertRaises(OSError):
            self.output.emit('Ctrl+C')
        cleanup = self.library.SendInput.call_args.args[1]
        self.assertEqual([(e.keyboard.vk, e.keyboard.flags) for e in cleanup], [(ord('C'), 2), (0xa2, 2)])

    def test_empty_and_closed_outputs_send_nothing(self):
        self.output.emit('')
        self.output.close()
        with self.assertRaises(OSError):
            self.output.emit('A')
        self.library.SendInput.assert_not_called()

    @patch('speededitor.battery.resolve_running', return_value=True)
    @patch('speededitor.battery.Device')
    def test_battery_does_not_open_controller_while_resolve_runs(self, device, running):
        from speededitor.battery import BatteryMonitor
        self.assertIn('Resolve', BatteryMonitor(queue.Queue()).check()[1])
        device.assert_not_called()
