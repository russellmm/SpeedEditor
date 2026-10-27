"""Small desktop editor for profiles and live device monitoring."""
from datetime import datetime
import json
from pathlib import Path
import queue
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk

from .device import discover
from .battery import BatteryMonitor
from .mapping import KEYS, MODES, ROOT, load_profile, parse_action, save_profile
from .worker import Worker


class App:
    def __init__(self, root):
        self.root = root
        root.title('SpeedEditor — Desktop & Resolve')
        root.geometry('1120x940')
        root.minsize(1000, 900)
        self.worker = Worker()
        self.profile_name = tk.StringVar(value='Desktop')
        self.status = tk.StringVar(value='Ready — connect to monitor or start mapping')
        self.battery = tk.StringVar(value='Battery: checking…')
        self.action = tk.StringVar()
        self.selected = tk.StringVar(value='Select a button below')
        self.profiles = {'Desktop': ROOT / 'profiles/desktop.json',
                         'Resolve shortcuts': ROOT / 'profiles/resolve.json'}
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
        style.configure('.', font=('DejaVu Sans', 10))
        style.configure('Title.TLabel', font=('DejaVu Sans', 22, 'bold'))
        self.table_font = tkfont.Font(root=self.root, family='DejaVu Sans', size=10)
        style.configure('Treeview', font=self.table_font,
                        rowheight=self.table_font.metrics('linespace') + 2)
        style.configure('Treeview.Heading', font=('DejaVu Sans', 10, 'bold'))
        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill='both', expand=True)
        title = ttk.Frame(outer)
        title.pack(fill='x')
        ttk.Label(title, text='SpeedEditor', style='Title.TLabel').pack(side='left')
        ttk.Label(title, textvariable=self.battery).pack(side='right')
        self.device_text = ttk.Label(outer, text='Checking device…')
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
        self.monitor_button = ttk.Button(controls, text='Monitor only', command=lambda: self.start(False))
        self.monitor_button.pack(side='right')
        self.start_button = ttk.Button(controls, text='Start mapping', command=lambda: self.start(True))
        self.start_button.pack(side='right', padx=6)
        self.stop_button = ttk.Button(controls, text='Stop', command=self.worker.stop, state='disabled')
        self.stop_button.pack(side='right')
        note = ('Desktop maps buttons to normal shortcuts. Resolve shortcuts is a starter preset, not native integration.\n'
                'For normal Resolve editing, choose “Use native Resolve” to release this controller before opening Resolve.')
        ttk.Label(outer, text=note, wraplength=1050, foreground='#555555').pack(anchor='w', pady=12)
        content = ttk.Panedwindow(outer, orient='horizontal')
        content.pack(fill='both', expand=True)
        left = ttk.Frame(content)
        right = ttk.Frame(content, padding=(18, 0, 0, 0))
        content.add(left, weight=3)
        content.add(right, weight=2)
        ttk.Label(left, text='BUTTON ASSIGNMENTS').pack(anchor='w', pady=(0, 6))
        frame = ttk.Frame(left)
        frame.pack(fill='both', expand=True)
        self.table = ttk.Treeview(frame, columns=('id', 'button', 'action'), show='headings', selectmode='browse')
        id_width = self.table_font.measure('0x3C') + 12
        for name, text, width in [('id', 'ID', id_width), ('button', 'Speed Editor button', 155), ('action', 'Shortcut', 180)]:
            self.table.heading(name, text=text)
            self.table.column(name, width=width, stretch=name != 'id')
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        self.table.tag_configure('held', background='#d4eee5')
        self.table.bind('<<TreeviewSelect>>', self.select_button)
        ttk.Label(right, text='EDIT SELECTED BUTTON').pack(anchor='w')
        ttk.Label(right, textvariable=self.selected, font=('DejaVu Sans', 13, 'bold')).pack(anchor='w', pady=8)
        self.action_entry = ttk.Entry(right, textvariable=self.action)
        self.action_entry.pack(fill='x')
        self.action_entry.bind('<Return>', lambda _: self.apply_button())
        ttk.Button(right, text='Apply & save', command=self.apply_button).pack(anchor='w', pady=8)
        ttk.Label(right, text='Examples: Ctrl+C, Alt+Tab, Super+E, Space,\nPlayPause, VolumeUp, ScrollDown.\nLeave blank to send nothing. Mode buttons also\nselect their wheel mode. Actions tap once per press.',
                  foreground='#555555').pack(anchor='w', pady=(0, 15))
        ttk.Label(right, text='WHEEL — BEHAVIOR / LEFT / RIGHT / THRESHOLD').pack(anchor='w')
        self.wheel_vars = {}
        self.wheel_behaviors = {}
        self.wheel_entries = {}
        for mode in MODES:
            row = ttk.Frame(right)
            row.pack(fill='x', pady=5)
            ttk.Label(row, text=mode, width=5).pack(side='left')
            behavior = tk.StringVar()
            self.wheel_behaviors[mode] = behavior
            picker = ttk.Combobox(row, textvariable=behavior, values=('Standard', 'Custom'), state='readonly', width=9)
            picker.pack(side='left', padx=2)
            picker.bind('<<ComboboxSelected>>', lambda _, selected_mode=mode: self.update_wheel_fields(selected_mode))
            variables = [tk.StringVar() for _ in range(3)]
            self.wheel_vars[mode] = variables
            self.wheel_entries[mode] = []
            for index, variable in enumerate(variables):
                entry = ttk.Entry(row, textvariable=variable, width=6 if index == 2 else 9)
                entry.pack(side='left', padx=2, fill='x', expand=index < 2)
                self.wheel_entries[mode].append(entry)
        ttk.Button(right, text='Save wheel settings', command=self.apply_wheel).pack(anchor='w', pady=5)
        ttk.Label(right, text='Standard: JOG = frames; SCRL = 10× frames;\nSHTL = latched J/K/L playback levels.\nCustom enables the left/right shortcut fields.\nLower threshold = more sensitive. Focus a video editor.',
                  foreground='#555555').pack(anchor='w', pady=5)
        ttk.Separator(right).pack(fill='x', pady=12)
        ttk.Button(right, text='Use native Resolve', command=self.native_resolve).pack(anchor='w')
        ttk.Label(right, text='Stops this mapper and gives Resolve control.\nCustom mappings are inactive while Resolve owns it.', foreground='#555555').pack(anchor='w', pady=5)
        bottom = ttk.Frame(outer)
        bottom.pack(fill='x', pady=(12, 5))
        ttk.Label(bottom, textvariable=self.status, wraplength=1000).pack(anchor='w')
        self.log = tk.Text(outer, height=5, font=('DejaVu Sans Mono', 9), state='disabled', background='#f0f2f4', relief='flat')
        self.log.pack(fill='x')

    def update_device(self):
        devices = discover()
        if devices:
            text = devices[0]['name'] + '  •  USB connected'
            if not devices[0]['accessible']:
                text += '  •  Device-access setup required'
        else:
            text = 'Speed Editor not connected — profile editing is available'
        self.device_text.configure(text=text)

    def refresh_table(self):
        selection = self.table.selection()
        self.table.delete(*self.table.get_children())
        for code, name in sorted(KEYS.items()):
            self.table.insert('', 'end', iid=name, values=(f'0x{code:02X}', name.replace('_', ' '), self.profile['buttons'][name] or '—'))
        if selection and self.table.exists(selection[0]):
            self.table.selection_set(selection[0])
        for mode, variables in self.wheel_vars.items():
            settings = self.profile['wheel'][mode]
            self.wheel_behaviors[mode].set(settings.get('behavior', 'custom').title())
            for variable, key in zip(variables, ('left', 'right', 'threshold')):
                variable.set(str(settings[key]))
            self.update_wheel_fields(mode)

    def update_wheel_fields(self, mode):
        standard = self.wheel_behaviors[mode].get() == 'Standard'
        for entry in self.wheel_entries[mode][:2]:
            entry.configure(state='disabled' if standard else 'normal')

    def select_button(self, _=None):
        selected = self.table.selection()
        if selected:
            self.selected.set(selected[0].replace('_', ' '))
            self.action.set(self.profile['buttons'][selected[0]])

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
        candidate['buttons'][selection[0]] = self.action.get().strip()
        self.persist(candidate)

    def apply_wheel(self):
        candidate = json.loads(json.dumps(self.profile))
        try:
            for mode, variables in self.wheel_vars.items():
                candidate['wheel'][mode] = dict(zip(('left', 'right', 'threshold'),
                                                   (variables[0].get().strip(), variables[1].get().strip(), int(variables[2].get()))))
                candidate['wheel'][mode]['behavior'] = self.wheel_behaviors[mode].get().lower()
        except ValueError:
            messagebox.showerror('Invalid threshold', 'Wheel threshold must be a whole number.')
            return
        self.persist(candidate)

    def switch_profile(self, _=None):
        self.load(self.profiles[self.profile_name.get()])

    def load(self, path):
        try:
            profile = load_profile(path)
        except (OSError, ValueError, KeyError, TypeError) as error:
            messagebox.showerror('Cannot open profile', str(error))
            return
        self.profile, self.path = profile, Path(path)
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
            self.worker.start(self.profile, active)
            self.start_button.configure(state='disabled')
            self.monitor_button.configure(state='disabled')
            self.stop_button.configure(state='normal')
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
                if count:
                    self.append_log(f'{mode} wheel {delta:+d} → {action or "no shortcut"} ×{count}')
            elif kind == 'battery':
                charging = 'Charging' if data['charging'] else 'Not charging'
                self.battery.set(f'Battery: {data["level"]}% • {charging}')
            elif kind == 'battery_unavailable':
                self.battery.set(data)
            elif kind == 'stopped':
                self.start_button.configure(state='normal')
                self.monitor_button.configure(state='normal')
                self.stop_button.configure(state='disabled')
                for name in KEYS.values():
                    self.table.item(name, tags=())
                self.update_device()
                if self.status.get() in ('Mapping active', 'Monitor connected — no shortcuts sent') or self.status.get().startswith('Releasing'):
                    self.status.set('Stopped — controller released')
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
    root = tk.Tk()
    App(root)
    root.mainloop()
