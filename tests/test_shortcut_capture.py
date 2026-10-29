import unittest

from speededitor.mapping import parse_action
from speededitor.shortcut_capture import shortcut_from_key


class ShortcutCaptureTests(unittest.TestCase):
    def test_control_comma_and_other_punctuation(self):
        self.assertEqual(shortcut_from_key('comma', 4), 'Ctrl+Comma')
        self.assertEqual(shortcut_from_key('comma', 4, windows=True), 'Ctrl+Comma')
        self.assertEqual(shortcut_from_key('period', 0), 'Dot')
        self.assertEqual(shortcut_from_key('bracketleft', 4), 'Ctrl+LeftBrace')

    def test_shifted_symbols_keep_physical_base_key_and_shift(self):
        for symbol, base in [('plus', 'Equal'), ('less', 'Comma'),
                             ('question', 'Slash'), ('at', '2')]:
            with self.subTest(symbol=symbol):
                action = shortcut_from_key(symbol, 4)
                self.assertEqual(parse_action(action), parse_action(f'Ctrl+Shift+{base}'))
        # Caps Lock can produce an uppercase keysym without Shift being held.
        self.assertEqual(shortcut_from_key('S', 2), 'S')
        self.assertEqual(shortcut_from_key('S', 5), 'Ctrl+Shift+S')

    def test_modifier_presses_wait_for_main_key_and_held_modifiers_are_used(self):
        for key in ('Control_L', 'Control_R', 'Shift_R', 'Alt_L', 'Super_L'):
            self.assertIsNone(shortcut_from_key(key))
        self.assertEqual(shortcut_from_key('F1', held={'Control_R', 'Shift_L'}), 'Ctrl+Shift+F1')
        self.assertEqual(shortcut_from_key('e', held={'Win_L'}, windows=True), 'Super+E')

    def test_windows_locks_and_extended_flag_do_not_add_modifiers(self):
        self.assertEqual(shortcut_from_key('Left', 0x8 | 0x80 | 0x40, windows=True), 'Left')
        self.assertEqual(shortcut_from_key('s', 0x10, windows=True), 'Alt+S')
        self.assertEqual(shortcut_from_key('s', 0x20000, windows=True), 'Alt+S')
        self.assertEqual(shortcut_from_key('s', 0x8), 'Alt+S')
        self.assertEqual(shortcut_from_key('e', 0x40), 'Super+E')

    def test_navigation_and_keypad_names_are_valid_profile_shortcuts(self):
        for symbol, name in [('Return', 'Enter'), ('BackSpace', 'Backspace'),
                             ('Prior', 'PageUp'), ('Next', 'PageDown'),
                             ('KP_Add', 'KPPlus'), ('KP_3', 'KP3'),
                             ('Print', 'PrintScreen')]:
            self.assertEqual(shortcut_from_key(symbol), name)
            parse_action(name)
        self.assertEqual(shortcut_from_key('ISO_Left_Tab'), 'Shift+Tab')

    def test_unknown_keys_are_rejected(self):
        for symbol in ('??', 'NoSymbol', 'NotAKey'):
            with self.assertRaises(ValueError):
                shortcut_from_key(symbol)
