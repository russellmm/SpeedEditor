"""Focused Tk shortcut recording; never hooks or emits system keyboard input."""
import tkinter as tk
from tkinter import ttk

from .mapping import parse_action


MODIFIERS = {'Control_L': 'Ctrl', 'Control_R': 'Ctrl',
             'Shift_L': 'Shift', 'Shift_R': 'Shift',
             'Alt_L': 'Alt', 'Alt_R': 'Alt',
             'Super_L': 'Super', 'Super_R': 'Super',
             'Meta_L': 'Super', 'Meta_R': 'Super',
             'Win_L': 'Super', 'Win_R': 'Super'}
KEY_NAMES = {'comma': 'Comma', 'period': 'Dot', 'slash': 'Slash',
             'semicolon': 'Semicolon', 'apostrophe': 'Apostrophe',
             'bracketleft': 'LeftBrace', 'bracketright': 'RightBrace',
             'backslash': 'Backslash', 'grave': 'Grave', 'minus': 'Minus',
             'equal': 'Equal', 'space': 'Space', 'Return': 'Enter',
             'BackSpace': 'Backspace', 'Prior': 'PageUp', 'Next': 'PageDown',
             'ISO_Left_Tab': 'Tab', 'Print': 'PrintScreen',
             'Caps_Lock': 'CapsLock', 'Num_Lock': 'NumLock',
             'Scroll_Lock': 'ScrollLock', 'Menu': 'Menu',
             'KP_Enter': 'Enter', 'KP_Add': 'KPPlus', 'KP_Subtract': 'KPMinus',
             'KP_Multiply': 'KPAsterisk', 'KP_Divide': 'KPSlash',
             'KP_Decimal': 'KPDot'}
KEY_NAMES.update({f'KP_{n}': f'KP{n}' for n in range(10)})
SHIFTED_KEYS = {'less': 'Comma', 'greater': 'Dot', 'question': 'Slash',
                'colon': 'Semicolon', 'quotedbl': 'Apostrophe',
                'braceleft': 'LeftBrace', 'braceright': 'RightBrace',
                'bar': 'Backslash', 'asciitilde': 'Grave',
                'underscore': 'Minus', 'plus': 'Equal',
                'exclam': '1', 'at': '2', 'numbersign': '3', 'dollar': '4',
                'percent': '5', 'asciicircum': '6', 'ampersand': '7',
                'asterisk': '8', 'parenleft': '9', 'parenright': '0',
                'ISO_Left_Tab': 'Tab'}


def shortcut_from_key(keysym, state=0, held=(), windows=False):
    """Convert a Tk key event to the existing US-style profile syntax.

    Tk's Windows Mod1 is Num Lock and Mod4 is the extended-key flag;
    neither should accidentally become Alt or Super. Windows Alt is Mod2
    (plus Tk's synthesized Alt bit). X11 uses the usual Mod1 Alt mapping.
    Tracked modifier presses also cover modifiers held inside the dialog.
    """
    if keysym in MODIFIERS:
        return None
    modifiers = {MODIFIERS[key] for key in held if key in MODIFIERS}
    if state & 0x4:
        modifiers.add('Ctrl')
    if state & 0x1 or keysym in SHIFTED_KEYS:
        modifiers.add('Shift')
    if state & (0x20010 if windows else 0x8):
        modifiers.add('Alt')
    if not windows and state & 0x40:
        modifiers.add('Super')
    key = SHIFTED_KEYS.get(keysym, KEY_NAMES.get(keysym, keysym))
    if len(key) == 1:
        key = key.upper()
    action = '+'.join([name for name in ('Ctrl', 'Alt', 'Shift', 'Super')
                       if name in modifiers] + [key])
    kind, _ = parse_action(action)
    if kind != 'keys':
        raise ValueError('This key cannot be recorded; enter its name manually')
    return action


class ShortcutRecorder:
    def __init__(self, parent, accept):
        self.accept = accept
        self.held = set()
        self.action = None
        self.previous_grab = parent.grab_current()
        self.window = tk.Toplevel(parent)
        self.window.withdraw()
        self.window.title('Record shortcut')
        self.window.transient(parent)
        self.window.resizable(False, False)
        self.windows = self.window.tk.call('tk', 'windowingsystem') == 'win32'
        body = ttk.Frame(self.window, padding=18)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Click below, then press your key combination.\n'
                            'Click Use shortcut when it looks right. Esc cancels.').pack(anchor='w')
        self.preview = tk.StringVar(master=parent, value='Press a shortcut…')
        self.capture = ttk.Frame(body, padding=20, takefocus=True, relief='sunken')
        self.capture.pack(fill='x', pady=12)
        label = ttk.Label(self.capture, textvariable=self.preview)
        label.pack()
        self.capture.bind('<Button-1>', lambda _: self.capture.focus_set())
        label.bind('<Button-1>', lambda _: self.capture.focus_set())
        self.capture.bind('<KeyPress>', self.key_press)
        self.capture.bind('<KeyRelease>', self.key_release)
        self.capture.bind('<FocusOut>', lambda _: self.held.clear())
        self.window.bind('<Escape>', lambda _: self.close())
        buttons = ttk.Frame(body)
        buttons.pack(fill='x')
        self.use_button = ttk.Button(buttons, text='Use shortcut', command=self.use,
                                     state='disabled')
        self.use_button.pack(side='left')
        ttk.Button(buttons, text='Cancel', command=self.close).pack(side='right')
        self.window.protocol('WM_DELETE_WINDOW', self.close)

    def show(self):
        self.window.deiconify()
        self.window.grab_set()
        self.capture.focus_set()

    def key_press(self, event):
        if event.keysym == 'Escape':
            self.close()
            return 'break'
        if event.keysym in MODIFIERS:
            self.held.add(event.keysym)
            return 'break'
        try:
            self.action = shortcut_from_key(event.keysym, event.state, self.held, self.windows)
        except ValueError:
            self.action = None
            self.preview.set('Unsupported key. Enter its name in the shortcut field.')
        else:
            self.preview.set(self.action)
        self.use_button.configure(state='normal' if self.action else 'disabled')
        return 'break'

    def key_release(self, event):
        self.held.discard(event.keysym)
        return 'break'

    def use(self):
        if self.action:
            self.accept(self.action)
            self.close()

    def close(self):
        self.window.destroy()
        if self.previous_grab is not None and self.previous_grab.winfo_exists():
            self.previous_grab.grab_set()
