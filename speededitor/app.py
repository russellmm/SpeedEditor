"""Small desktop editor for profiles and live device monitoring."""
from datetime import datetime
import os
import json
from pathlib import Path
import queue
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk

from .device import discover
from .battery import BatteryMonitor
from .mapping import KEYS, MODES, ROOT, load_profile, parse_action, save_profile
from .shortcut_capture import ShortcutRecorder
from .measured_editor import MeasuredTransportEditor
from .measured_transport import settings_for
from .worker import Worker

DESKTOP_MODE = 'Desktop shortcuts'
RESOLVE_MODE = 'Resolve native wheel (experimental)'

def configure_display():
    """Use physical screen coordinates before Tk creates windows on Windows."""
    if os.name == 'nt':
        import ctypes
        user = ctypes.WinDLL('user32', use_last_error=True)
        user.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))


class App:
    def __init__(self, root):
        self.root = root
        root.title('SpeedEditor — Desktop & Resolve')
        # Fit Windows displays with 125–200% scaling as well as Linux desktops.
        display_scale = max(1.0, float(root.tk.call('tk', 'scaling')) / (96 / 72))
        width = min(round(1120 * display_scale), max(800, root.winfo_screenwidth() - 80))
        height = min(round(940 * display_scale), max(600, root.winfo_screenheight() - 120))
        root.geometry(f'{width}x{height}')
        self.initial_width = width
        root.minsize(min(1000, width), min(760, height))
        self.font_family = 'Segoe UI' if os.name == 'nt' else 'DejaVu Sans'
        self.worker = Worker()
        self.profile_name = tk.StringVar(value='Desktop')
        self.connection_mode = tk.StringVar(value=DESKTOP_MODE)
        self.button_behavior = tk.StringVar(value='Shortcut')
        self.native_wheel_status = tk.StringVar(value='')
        self.status = tk.StringVar(value='Ready — connect to monitor or start mapping')
        self.battery = tk.StringVar(value='Battery: checking…')
        self.action = tk.StringVar()
        self.selected = tk.StringVar(value='Select a button below')
        self.profiles = {'Desktop': ROOT / 'profiles/desktop.json',
                         'Resolve shortcuts': ROOT / 'profiles/resolve.json',
                         'Resolve native wheel': ROOT / 'profiles/resolve-native.json'}
        self.profile = load_profile(self.profiles['Desktop'])
        self.path = self.profiles['Desktop']
        self.make_ui()
        self.refresh_table()
        self.update_device()
        self.battery_monitor = BatteryMonitor(self.worker.events)
        self.battery_monitor.start()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(80, self.poll)

    def make_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', font=(self.font_family, 10))
        style.configure('Title.TLabel', font=(self.font_family, 22, 'bold'))
        self.table_font = tkfont.Font(root=self.root, family=self.font_family, size=10)
        style.configure('Treeview', font=self.table_font,
                        rowheight=self.table_font.metrics('linespace') + 2)
        style.configure('Treeview.Heading', font=(self.font_family, 10, 'bold'))
        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill='both', expand=True)
        title = ttk.Frame(outer)
        title.pack(fill='x')
        ttk.Label(title, text='SpeedEditor', style='Title.TLabel').pack(side='left')
        ttk.Label(title, textvariable=self.battery).pack(side='right')
        self.device_text = ttk.Label(outer, text='Checking device…')
        self.device_text.configure(wraplength=self.initial_width - 40)
        self.device_text.pack(anchor='w', pady=(5, 12))
        controls = ttk.Frame(outer)
        controls.pack(fill='x')
        ttk.Label(controls, text='Profile').pack(side='left', padx=(0, 8))
        self.profile_picker = ttk.Combobox(controls, textvariable=self.profile_name,
                                          values=list(self.profiles), state='readonly', width=21)
        self.profile_picker.pack(side='left')
        self.profile_picker.bind('<<ComboboxSelected>>', self.switch_profile)
        ttk.Button(controls, text='Open…', command=self.open_profile).pack(side='left', padx=5)
        ttk.Button(controls, text='Save as…', command=self.save_as).pack(side='left')
        connection = ttk.Frame(outer)
        connection.pack(fill='x', pady=(8, 0))
        ttk.Label(connection, text='Control mode').pack(side='left', padx=(0, 8))
        self.connection_picker = ttk.Combobox(connection, textvariable=self.connection_mode,
                                              values=(DESKTOP_MODE, RESOLVE_MODE), width=39, state='readonly')
        self.connection_picker.pack(side='left')
        self.connection_picker.bind('<<ComboboxSelected>>', self.change_connection_mode)
        ttk.Label(connection, textvariable=self.native_wheel_status).pack(side='left', padx=10)
        transport = ttk.Frame(outer)
        transport.pack(fill='x', pady=(8, 0))
        self.stop_button = ttk.Button(transport, text='Stop', command=self.worker.stop, state='disabled')
        self.stop_button.pack(side='left')
        self.start_button = ttk.Button(transport, text='Start mapping', command=lambda: self.start(True))
        self.start_button.pack(side='left', padx=6)
        self.monitor_button = ttk.Button(transport, text='Monitor only', command=lambda: self.start(False))
        self.monitor_button.pack(side='left')
        self.mode_note = tk.StringVar()
        note_label = ttk.Label(outer, textvariable=self.mode_note, wraplength=self.initial_width - 40, foreground='#555555')
        note_label.pack(anchor='w', pady=12)
        outer.bind('<Configure>', lambda event: (note_label.configure(wraplength=max(200, event.width - 40)),
                   self.device_text.configure(wraplength=max(200, event.width - 40))))
        content = ttk.Panedwindow(outer, orient='horizontal')
        content.pack(fill='both', expand=True)
        left = ttk.Frame(content)
        right_panel = ttk.Frame(content)
        right_canvas = tk.Canvas(right_panel, highlightthickness=0, borderwidth=0)
        right_scroll = ttk.Scrollbar(right_panel, orient='vertical', command=right_canvas.yview)
        right_canvas.configure(yscrollcommand=right_scroll.set)
        right_scroll.pack(side='right', fill='y')
        right_canvas.pack(side='left', fill='both', expand=True)
        right = ttk.Frame(right_canvas, padding=(18, 0, 0, 0))
        right_window = right_canvas.create_window((0, 0), window=right, anchor='nw')
        right.bind('<Configure>', lambda _: right_canvas.configure(scrollregion=right_canvas.bbox('all')))
        right_canvas.bind('<Configure>', lambda event: right_canvas.itemconfigure(right_window, width=event.width))
        content.add(left, weight=3)
        content.add(right_panel, weight=2)
        ttk.Label(left, text='BUTTON ASSIGNMENTS').pack(anchor='w', pady=(0, 6))
        frame = ttk.Frame(left)
        frame.pack(fill='both', expand=True)
        self.table = ttk.Treeview(frame, columns=('id', 'button', 'action'), show='headings', selectmode='browse')
        id_width = self.table_font.measure('0x3C') + 12
        button_width = max(self.table_font.measure(name.replace('_', ' ')) for name in KEYS.values()) + 18
        action_width = self.table_font.measure('Ctrl+Shift+Tab') + 18
        for name, text, width in [('id', 'ID', id_width), ('button', 'Button', button_width), ('action', 'Shortcut', action_width)]:
            self.table.heading(name, text=text)
            self.table.column(name, width=width, minwidth=width, stretch=name != 'id')
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=self.table.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=self.table.xview)
        self.table.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
        horizontal.pack(side='bottom', fill='x')
        self.table.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        self.table.tag_configure('held', background='#d4eee5')
        self.table.bind('<<TreeviewSelect>>', self.select_button)
        ttk.Label(right, text='EDIT SELECTED BUTTON').pack(anchor='w')
        ttk.Label(right, textvariable=self.selected, font=(self.font_family, 13, 'bold')).pack(anchor='w', pady=8)
        self.button_behavior_picker = ttk.Combobox(right, textvariable=self.button_behavior,
                                                   values=('Native', 'Shortcut', 'Disabled'), state='disabled', width=18)
        self.button_behavior_picker.pack(anchor='w', pady=(0, 5))
        self.button_behavior_picker.bind('<<ComboboxSelected>>', lambda _: self.update_button_fields())
        self.action_entry = ttk.Entry(right, textvariable=self.action)
        self.action_entry.pack(fill='x')
        self.action_entry.bind('<Return>', lambda _: self.apply_button())
        button_actions = ttk.Frame(right)
        button_actions.pack(fill='x', pady=8)
        self.record_button = ttk.Button(button_actions, text='Record shortcut…', command=self.record_shortcut,
                                        state='disabled')
        self.record_button.pack(side='left', padx=(0, 8))
        ttk.Button(button_actions, text='Apply & save', command=self.apply_button).pack(side='left')
        self.button_note = tk.StringVar()
        ttk.Label(right, textvariable=self.button_note, foreground='#555555').pack(anchor='w', pady=(0, 15))
        ttk.Label(right, text='WHEEL — BEHAVIOR / LEFT / RIGHT / THRESHOLD').pack(anchor='w')
        self.wheel_vars = {}
        self.wheel_behaviors = {}
        self.wheel_entries = {}
        self.wheel_pickers = {}
        for mode in MODES:
            row = ttk.Frame(right)
            row.pack(fill='x', pady=5)
            ttk.Label(row, text=mode, width=5).pack(side='left')
            behavior = tk.StringVar()
            self.wheel_behaviors[mode] = behavior
            picker = ttk.Combobox(row, textvariable=behavior, values=('Standard', 'Custom', 'Measured'), state='readonly', width=9)
            picker.pack(side='left', padx=2)
            self.wheel_pickers[mode] = picker
            picker.bind('<<ComboboxSelected>>', lambda _, selected_mode=mode: self.update_wheel_fields(selected_mode))
            variables = [tk.StringVar() for _ in range(3)]
            self.wheel_vars[mode] = variables
            self.wheel_entries[mode] = []
            for index, variable in enumerate(variables):
                entry = ttk.Entry(row, textvariable=variable, width=6 if index == 2 else 9)
                entry.pack(side='left', padx=2, fill='x', expand=index < 2)
                self.wheel_entries[mode].append(entry)
        self.wheel_save = ttk.Button(right, text='Save wheel settings', command=self.apply_wheel)
        self.wheel_save.pack(anchor='w', pady=5)
        self.measured_setup = ttk.Button(right, text='Measured transport settings…', command=self.edit_measured_transport)
        self.measured_setup.pack(anchor='w', pady=(0, 5))
        self.wheel_note = tk.StringVar()
        ttk.Label(right, textvariable=self.wheel_note, foreground='#555555').pack(anchor='w', pady=5)
        ttk.Separator(right).pack(fill='x', pady=12)
        ttk.Button(right, text='Use native Resolve', command=self.native_resolve).pack(anchor='w')
        ttk.Label(right, text='Stops desktop mapping or detaches the Resolve adapter.\nAll buttons then use normal native Resolve behavior.', foreground='#555555').pack(anchor='w', pady=5)
        bottom = ttk.Frame(outer)
        bottom.pack(fill='x', pady=(12, 5))
        ttk.Label(bottom, textvariable=self.status, wraplength=1000).pack(anchor='w')
        self.log = tk.Text(outer, height=5, font=('Consolas' if os.name == 'nt' else 'DejaVu Sans Mono', 9), state='disabled', background='#f0f2f4', relief='flat')
        self.log.pack(fill='x')
        # Reserve bottom status/log space before the expanding editor consumes it.
        content.pack_forget()
        bottom.pack_forget()
        self.log.pack_forget()
        self.log.pack(side='bottom', fill='x')
        bottom.pack(side='bottom', fill='x', pady=(12, 5))
        content.pack(fill='both', expand=True)
        self.update_mode_notes()

    def update_device(self):
        try:
            devices = discover()
        except (OSError, ImportError) as error:
            self.device_text.configure(text=f'Device discovery unavailable: {error}')
            return
        if devices:
            text = devices[0]['name'] + '  •  USB connected'
            if not devices[0]['accessible']:
                text += '  •  ' + devices[0].get('reason', 'Device-access setup required')
        else:
            text = 'Speed Editor not connected — profile editing is available'
        self.device_text.configure(text=text)

    def refresh_table(self):
        selection = self.table.selection()
        self.table.delete(*self.table.get_children())
        for code, name in sorted(KEYS.items()):
            if self.connection_mode.get() == RESOLVE_MODE:
                overrides = self.profile.get('resolve_buttons', {})
                action = ('Native — wheel mode' if name in MODES else
                          'Native' if name not in overrides else overrides[name] or 'Disabled')
            else:
                action = self.profile['buttons'][name] or '—'
            self.table.insert('', 'end', iid=name, values=(f'0x{code:02X}', name.replace('_', ' '), action))
        if selection and self.table.exists(selection[0]):
            self.table.selection_set(selection[0])
        for mode, variables in self.wheel_vars.items():
            settings = self.profile['wheel'][mode]
            self.wheel_behaviors[mode].set(settings.get('behavior', 'custom').title())
            for variable, key in zip(variables, ('left', 'right', 'threshold')):
                variable.set(str(settings[key]))
            self.update_wheel_fields(mode)
        self.select_button()

    def update_wheel_fields(self, mode):
        native = self.connection_mode.get() == RESOLVE_MODE
        standard = self.wheel_behaviors[mode].get() == 'Standard'
        measured = self.wheel_behaviors[mode].get() == 'Measured'
        self.wheel_pickers[mode].configure(state='disabled' if native else 'readonly')
        for entry in self.wheel_entries[mode][:2]:
            entry.configure(state='disabled' if native or standard or (measured and mode == 'SHTL') else 'normal')
        self.wheel_entries[mode][2].configure(state='disabled' if native or measured else 'normal')
        self.wheel_save.configure(state='disabled' if native else 'normal')
        self.measured_setup.configure(state='disabled' if native else 'normal')

    def update_mode_notes(self):
        native = self.connection_mode.get() == RESOLVE_MODE
        self.stop_button.configure(text='Stop adapter' if native else 'Stop')
        self.mode_note.set('Experimental Windows adapter: Resolve keeps native wheel control. Explicit button overrides replace native button actions.\n'
                           'All buttons start Native. Start mapping attaches the runtime adapter; Stop restores native buttons.' if native else
                           'Desktop shortcuts use keyboard transport emulation. Resolve must be closed for desktop mapping.\n'
                           'Choose Resolve native wheel mode to program button overrides while Resolve is running.')
        self.button_note.set('Native keeps Resolve’s action; Shortcut replaces it;\nDisabled suppresses it. JOG, SCRL and SHTL stay native.\nShortcuts run only while Resolve has focus.\nExamples: Ctrl+C, Space, Ctrl+Shift+S.\nPunctuation: Ctrl+, or Ctrl+Comma.' if native else
                             'Examples: Ctrl+C, Alt+Tab, Super+E, Space,\nPlayPause, VolumeUp, ScrollDown, Ctrl+,.\nLeave blank to send nothing. Actions tap once per press.')
        self.wheel_note.set('Native wheel: Resolve controls JOG, SCRL and SHTL.\nWheel shortcuts and thresholds are inactive here.\nThe measured speed curve is reference data;\nwheel input passes through to Resolve unchanged.' if native else
                            'Standard: JOG = frames; SCRL = 10× frames;\nSHTL = latched J/K/L playback levels.\nCustom enables left/right shortcuts.\nMeasured (experimental) uses captured input scales:\nconfigure steps/turn and SHTL output below.\nKeyboard output remains an approximation.')

    def change_connection_mode(self, _=None):
        if self.worker.running:
            return
        self.update_mode_notes()
        self.native_wheel_status.set('Native wheel' if self.connection_mode.get() == RESOLVE_MODE else '')
        self.refresh_table()
        self.update_button_fields()

    def update_button_fields(self):
        selection = self.table.selection()
        native = self.connection_mode.get() == RESOLVE_MODE
        reserved = bool(selection and selection[0] in MODES)
        if reserved and native:
            self.button_behavior.set('Native')
        self.button_behavior_picker.configure(state='readonly' if native and not reserved else 'disabled')
        editable = bool(selection) and not (native and (reserved or self.button_behavior.get() != 'Shortcut'))
        self.action_entry.configure(state='normal' if editable else 'disabled')
        self.record_button.configure(state='normal' if editable else 'disabled')

    def record_shortcut(self):
        self.update_button_fields()
        if self.record_button.instate(['disabled']):
            return
        recorder = ShortcutRecorder(self.root, self.action.set)
        recorder.show()
        return recorder

    def select_button(self, _=None):
        selected = self.table.selection()
        if selected:
            self.selected.set(selected[0].replace('_', ' '))
            name = selected[0]
            if self.connection_mode.get() == RESOLVE_MODE:
                overrides = self.profile.get('resolve_buttons', {})
                self.button_behavior.set('Native' if name not in overrides or name in MODES else
                                         'Shortcut' if overrides[name] else 'Disabled')
                self.action.set(overrides.get(name, ''))
            else:
                self.button_behavior.set('Shortcut')
                self.action.set(self.profile['buttons'][name])
        self.update_button_fields()

    def persist(self, candidate):
        try:
            save_profile(self.path, candidate)
        except (OSError, ValueError, KeyError) as error:
            messagebox.showerror('Cannot save profile', str(error))
            return False
        self.profile = candidate
        self.worker.update(self.profile)
        self.refresh_table()
        self.status.set(f'Saved {self.path.name}')
        return True

    def apply_button(self):
        selection = self.table.selection()
        if not selection:
            return
        candidate = json.loads(json.dumps(self.profile))
        name = selection[0]
        if self.connection_mode.get() == RESOLVE_MODE:
            if name in MODES:
                self.status.set('JOG, SCRL and SHTL are reserved for native wheel control')
                return
            overrides = candidate.setdefault('resolve_buttons', {})
            behavior = self.button_behavior.get()
            if behavior == 'Native':
                overrides.pop(name, None)
            elif behavior == 'Disabled':
                overrides[name] = ''
            else:
                action = self.action.get().strip()
                if not action or action == 'None':
                    self.status.set('Enter a shortcut, or choose Native / Disabled')
                    return
                overrides[name] = action
        else:
            candidate['buttons'][name] = self.action.get().strip()
        self.persist(candidate)

    def apply_wheel(self):
        if self.connection_mode.get() == RESOLVE_MODE:
            self.status.set('Resolve owns the native wheel; desktop wheel settings are inactive')
            return
        try:
            candidate = self.wheel_candidate()
        except ValueError:
            messagebox.showerror('Invalid threshold', 'Wheel threshold must be a whole number.')
            return
        self.persist(candidate)

    def wheel_candidate(self):
        candidate = json.loads(json.dumps(self.profile))
        for mode, variables in self.wheel_vars.items():
            candidate['wheel'][mode].update(left=variables[0].get().strip(), right=variables[1].get().strip(),
                                            threshold=int(variables[2].get()),
                                            behavior=self.wheel_behaviors[mode].get().lower())
        return candidate

    def edit_measured_transport(self):
        if self.connection_mode.get() == RESOLVE_MODE:
            return
        editor = MeasuredTransportEditor(self.root, settings_for(self.profile), self.save_measured_transport)
        editor.show()
        return editor

    def save_measured_transport(self, settings):
        try:
            candidate = self.wheel_candidate()
        except ValueError:
            messagebox.showerror('Invalid threshold', 'Wheel threshold must be a whole number.')
            return False
        candidate['measured_transport'] = settings
        return self.persist(candidate)

    def switch_profile(self, _=None):
        self.load(self.profiles[self.profile_name.get()])

    def load(self, path):
        try:
            profile = load_profile(path)
        except (OSError, ValueError, KeyError, TypeError) as error:
            messagebox.showerror('Cannot open profile', str(error))
            return
        self.profile, self.path = profile, Path(path)
        if profile.get('preferred_control_mode') == 'resolve_native' and not self.worker.running:
            self.connection_mode.set(RESOLVE_MODE)
            self.update_mode_notes()
            self.native_wheel_status.set('Native wheel')
        self.worker.update(profile)
        self.action.set('')
        self.selected.set('Select a button below')
        self.refresh_table()
        self.status.set(f'Loaded {profile["name"]}')

    def open_profile(self):
        path = filedialog.askopenfilename(initialdir=ROOT / 'profiles', filetypes=[('Profiles', '*.json')])
        if path:
            self.register_custom(Path(path))
            self.load(path)

    def register_custom(self, path):
        name = f'Custom: {path.stem}'
        self.profiles[name] = path
        self.profile_picker.configure(values=list(self.profiles))
        self.profile_name.set(name)

    def save_as(self):
        path = filedialog.asksaveasfilename(initialdir=ROOT / 'profiles', defaultextension='.json', filetypes=[('Profiles', '*.json')])
        if path:
            try:
                save_profile(path, self.profile)
            except (OSError, ValueError) as error:
                messagebox.showerror('Cannot save profile', str(error))
                return
            self.path = Path(path)
            self.register_custom(self.path)
            self.status.set(f'Saved {self.path.name}')

    def start(self, active):
        try:
            native = self.connection_mode.get() == RESOLVE_MODE
            self.worker.start(self.profile, active, native_resolve=native)
            self.start_button.configure(state='disabled')
            self.monitor_button.configure(state='disabled')
            self.stop_button.configure(state='normal')
            self.connection_picker.configure(state='disabled')
            self.status.set('Connecting…')
        except RuntimeError as error:
            self.status.set(str(error))

    def native_resolve(self):
        self.worker.stop()
        self.status.set('Releasing controller for native Resolve…' if self.worker.running else 'Native Resolve mode — mapper disconnected')

    def append_log(self, line):
        self.log.configure(state='normal')
        self.log.insert('end', f'{datetime.now():%H:%M:%S}  {line}\n')
        if int(self.log.index('end-1c').split('.')[0]) > 150:
            self.log.delete('1.0', '50.0')
        self.log.see('end')
        self.log.configure(state='disabled')

    def poll(self):
        while True:
            try:
                kind, data = self.worker.events.get_nowait()
            except queue.Empty:
                break
            if kind in ('status', 'error'):
                self.status.set(data)
                self.append_log(data)
            elif kind == 'keys':
                held, events, mode = data
                for code, name in KEYS.items():
                    self.table.item(name, tags=('held',) if code in held else ())
                for name, action in events:
                    self.append_log(f'{name} → {action or "no shortcut"}  [{mode}]')
            elif kind == 'wheel':
                delta, action, count, mode = data
                if action.startswith('Measured target'):
                    self.append_log(f'{mode} position {delta:+d}: {action}')
                elif count:
                    self.append_log(f'{mode} wheel {delta:+d} → {action or "no shortcut"} ×{count}')
            elif kind == 'native_wheel':
                _, _, mode = data
                self.native_wheel_status.set(f'Native wheel: {mode}')
            elif kind == 'status_action':
                name, action = data
                self.append_log(f'{name} → {action}  [Resolve button override]')
            elif kind == 'battery':
                charging = 'Charging' if data['charging'] else 'Not charging'
                self.battery.set(f'Battery: {data["level"]}% • {charging}')
            elif kind == 'battery_unavailable':
                self.battery.set(data)
            elif kind == 'stopped':
                self.start_button.configure(state='normal')
                self.monitor_button.configure(state='normal')
                self.stop_button.configure(state='disabled')
                self.connection_picker.configure(state='readonly')
                for name in KEYS.values():
                    self.table.item(name, tags=())
                self.update_device()
                if self.status.get() in ('Mapping active', 'Monitor connected — no shortcuts sent') or self.status.get().startswith('Releasing'):
                    self.status.set('Stopped — controller released')
                elif self.status.get().startswith(('Resolve button mapping active', 'Resolve monitor connected', 'Resolve adapter connected')):
                    self.status.set('Stopped — Resolve adapter detached; all buttons native')
        self.root.after(80, self.poll)

    def close(self):
        self.worker.stop()
        self.battery_monitor.stop()
        self.root.after(100, self.finish_close)

    def finish_close(self):
        if self.worker.running or self.battery_monitor.running:
            self.root.after(100, self.finish_close)
        else:
            self.root.destroy()


def main():
    configure_display()
    root = tk.Tk()
    App(root)
    root.mainloop()
