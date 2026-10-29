import copy
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import unittest
from unittest.mock import Mock, patch

from speededitor.mapping import ROOT, load_profile, validate
from speededitor.resolve_bridge import ResolveBridge, native_rules


class ResolveProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile(ROOT / 'profiles/desktop.json')

    def test_legacy_profiles_default_to_native_buttons_in_resolve(self):
        original = copy.deepcopy(self.profile)
        self.assertEqual(native_rules(self.profile), {})
        self.assertEqual(self.profile, original)

    def test_explicit_shortcut_and_disabled_buttons_only(self):
        self.profile['resolve_buttons'] = {'CAM9': 'Space', 'CAM1': ''}
        self.assertEqual(native_rules(self.profile), {'51': '', '59': 'Space'})

    def test_mode_buttons_and_unknown_names_cannot_be_overridden(self):
        for rules in ([], {'JOG': 'Space'}, {'SCRL': ''}, {'SHTL': 'K'}, {'UNKNOWN': 'C'}, {'CAM1': 42}):
            candidate = copy.deepcopy(self.profile)
            candidate['resolve_buttons'] = rules
            with self.assertRaises(ValueError):
                validate(candidate)

    @unittest.skipUnless(shutil.which('node'), 'Node.js required for the actual JavaScript adapter tests')
    def test_actual_javascript_routing_and_hooks(self):
        result = subprocess.run([shutil.which('node'), str(Path(__file__).with_name('resolve_bridge_test.js'))],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ResolveWorkerTests(unittest.TestCase):
    def setUp(self):
        self.events, self.commands = queue.Queue(), queue.Queue()
        self.stop = threading.Event()
        self.bridge = ResolveBridge(self.events, self.commands, self.stop)
        self.profile = load_profile(ROOT / 'profiles/desktop.json')
        self.profile['resolve_buttons'] = {'CAM9': 'Space'}

    def run_bridge(self, active, focused=True, fail_emit=False):
        frida = Mock()
        session = frida.get_local_device.return_value.attach.return_value
        script = session.create_script.return_value
        script.exports_sync.heartbeat.return_value = {'pid': 47, 'armed': True}
        def loaded():
            self.bridge.message({'type': 'send', 'payload': {'kind': 'keys', 'held': [59],
                                 'actions': [{'key': 59, 'action': 'Space'}]}})
            self.bridge.message({'type': 'send', 'payload': {'kind': 'wheel', 'hardware_mode': 3, 'value': 240}})
            self.bridge.message({'type': 'send', 'payload': {'kind': 'fault', 'error': 'test disconnect'}})
        script.load.side_effect = loaded
        with patch.dict(sys.modules, {'frida': frida}), \
             patch('speededitor.resolve_bridge.os.name', 'nt'), \
             patch('speededitor.resolve_bridge.resolve_process_ids', return_value=[47]), \
             patch('speededitor.resolve_bridge.ResolveBridgeLock'), \
             patch('speededitor.resolve_bridge.foreground_process_id', return_value=47 if focused else 99), \
             patch('speededitor.resolve_bridge.WindowsOutput') as output:
            if fail_emit:
                output.return_value.emit.side_effect = OSError('blocked')
            self.bridge.run(self.profile, active)
            return session, script, output

    def test_monitor_does_not_create_output_and_detaches(self):
        session, script, output = self.run_bridge(False)
        output.assert_not_called()
        script.exports_sync.configure.assert_any_call({'rules': {'59': 'Space'}, 'enabled': False})
        script.exports_sync.configure.assert_called_with({'rules': {}, 'enabled': False})
        script.unload.assert_called_once()
        session.detach.assert_called_once()
        self.assertIn('native_wheel', [event[0] for event in self.events.queue])
        self.assertEqual(list(self.events.queue)[-1], ('stopped', None))

    def test_explicit_mapping_emits_and_cleanup_restores_native(self):
        session, script, output = self.run_bridge(True)
        output.return_value.emit.assert_called_once_with('Space')
        output.return_value.close.assert_called_once()
        script.exports_sync.configure.assert_called_with({'rules': {}, 'enabled': False})
        session.detach.assert_called_once()

    def test_focus_change_after_script_message_drops_shortcut(self):
        _, _, output = self.run_bridge(True, focused=False)
        output.return_value.emit.assert_not_called()

    def test_delivery_failure_still_unloads_and_detaches(self):
        session, script, output = self.run_bridge(True, fail_emit=True)
        script.unload.assert_called_once()
        session.detach.assert_called_once()
        output.return_value.close.assert_called_once()

    def test_script_error_becomes_fault(self):
        self.bridge.message({'type': 'error', 'description': 'script failure'})
        self.assertEqual(self.bridge.incoming.get(), {'kind': 'fault', 'error': 'script failure'})

    def test_queue_overflow_stops_worker(self):
        self.bridge.incoming = queue.Queue(maxsize=1)
        self.bridge.message({'type': 'send', 'payload': {'kind': 'ready'}})
        self.bridge.message({'type': 'send', 'payload': {'kind': 'ready'}})
        self.assertTrue(self.stop.is_set())

    def test_multiple_resolve_instances_are_rejected_without_attach(self):
        with patch.dict(sys.modules, {'frida': Mock()}), \
             patch('speededitor.resolve_bridge.os.name', 'nt'), \
             patch('speededitor.resolve_bridge.resolve_process_ids', return_value=[47, 48]):
            self.bridge.run(self.profile)
        self.assertIn('one DaVinci Resolve', self.events.get()[1])
