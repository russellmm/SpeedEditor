"""Desktop-only editor for measured input calibration and application shortcuts."""
from copy import deepcopy
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from .mapping import parse_action
from .measured_transport import sample_points, speed_key, validate_settings
from .shortcut_capture import ShortcutRecorder


APPROXIMATE = 'Approximate J/K/L'
SHORTCUTS = 'Per-speed shortcuts'


class MeasuredTransportEditor:
    def __init__(self, parent, settings, save):
        self.settings = deepcopy(settings)
        self.actions = dict(settings['shuttle_actions'])
        self.save = save
        self.window = tk.Toplevel(parent)
        self.window.withdraw()
        self.window.title('Measured desktop transport — experimental')
        self.window.transient(parent)
        self.window.minsize(540, 460)
        body = ttk.Frame(self.window, padding=14)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Cut / Source Tape samples estimate wheel response. Transition boundaries\n'
                            'and JOG/SCRL frame gains were not measured. Resolve must be closed\n'
                            'for desktop USB ownership; use its native-wheel adapter while it is open.').pack(anchor='w')
        gains = ttk.Frame(body)
        gains.pack(fill='x', pady=10)
        self.steps = {}
        for mode in ('JOG', 'SCRL'):
            ttk.Label(gains, text=f'{mode} steps/turn').pack(side='left')
            variable = tk.StringVar(master=parent, value=str(settings['steps_per_turn'][mode]))
            self.steps[mode] = variable
            ttk.Entry(gains, textvariable=variable, width=7).pack(side='left', padx=(4, 14))
        ttk.Label(body, text='60 JOG / 600 SCRL are starting gains you can change, not native frame counts.').pack(anchor='w')
        stop_row = ttk.Frame(body)
        stop_row.pack(fill='x', pady=10)
        ttk.Label(stop_row, text='Stop shortcut').pack(side='left')
        self.stop = tk.StringVar(master=parent, value=settings['stop'])
        ttk.Entry(stop_row, textvariable=self.stop, width=20).pack(side='left', padx=8)
        ttk.Button(stop_row, text='Record…', command=lambda: self.record(self.stop)).pack(side='left')
        output_row = ttk.Frame(body)
        output_row.pack(fill='x')
        ttk.Label(output_row, text='SHTL output').pack(side='left')
        self.output = tk.StringVar(master=parent, value=SHORTCUTS if settings['output'] == 'shortcuts' else APPROXIMATE)
        picker = ttk.Combobox(output_row, textvariable=self.output,
                              values=(APPROXIMATE, SHORTCUTS), state='readonly', width=24)
        picker.pack(side='left', padx=8)
        picker.bind('<<ComboboxSelected>>', lambda _: self.update_fields())
        ttk.Label(body, text='Approximate: stop, then J/L taps at nominal 1/2/4/8/16/32/64× levels.\n'
                            'Fractional / odd speeds round to a level; actual rates depend on your editor.\n'
                            'Per-speed: assign a direct rate shortcut in your editor. Blank = stop.').pack(anchor='w', pady=8)
        table_frame = ttk.Frame(body)
        table_frame.pack(fill='both', expand=True)
        self.table = ttk.Treeview(table_frame, columns=('speed', 'position', 'action'), show='headings',
                                  selectmode='browse', height=8)
        heading_font = tkfont.Font(root=self.window, font=ttk.Style(self.window).lookup('Treeview.Heading', 'font'))
        for name, title in [('speed', 'Target speed'), ('position', 'Sample position'),
                             ('action', 'Application shortcut')]:
            width = heading_font.measure(title) + 20
            self.table.heading(name, text=title)
            self.table.column(name, width=width, minwidth=width, stretch=name == 'action')
        scroll = ttk.Scrollbar(table_frame, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        for position, speed in sample_points():
            if speed:
                key = speed_key(speed)
                self.table.insert('', 'end', iid=key,
                                  values=(f'{speed:+g}×', f'{position:+g}', self.actions.get(key, '') or 'Unassigned'))
        self.table.bind('<<TreeviewSelect>>', self.select)
        edit = ttk.Frame(body)
        edit.pack(fill='x', pady=8)
        self.action = tk.StringVar(master=parent)
        self.entry = ttk.Entry(edit, textvariable=self.action)
        self.entry.pack(side='left', fill='x', expand=True)
        self.record_button = ttk.Button(edit, text='Record…', command=lambda: self.record(self.action))
        self.record_button.pack(side='left', padx=5)
        self.assign_button = ttk.Button(edit, text='Assign', command=self.assign)
        self.assign_button.pack(side='left')
        self.status = tk.StringVar(master=parent, value='Reverse uses only sampled reverse rates; gaps are not mirrored.')
        ttk.Label(body, textvariable=self.status, wraplength=600).pack(anchor='w')
        buttons = ttk.Frame(body)
        buttons.pack(fill='x', pady=(12, 0))
        ttk.Button(buttons, text='Save settings', command=self.commit).pack(side='left')
        ttk.Button(buttons, text='Cancel', command=self.window.destroy).pack(side='right')
        self.update_fields()

    def show(self):
        self.window.deiconify()
        self.window.grab_set()

    def update_fields(self):
        editable = self.output.get() == SHORTCUTS and bool(self.table.selection())
        for widget in (self.entry, self.record_button, self.assign_button):
            widget.configure(state='normal' if editable else 'disabled')

    def select(self, _=None):
        selected = self.table.selection()
        if selected:
            self.action.set(self.actions.get(selected[0], ''))
        self.update_fields()

    def assign(self):
        selected = self.table.selection()
        if not selected or self.output.get() != SHORTCUTS:
            return True
        action = self.action.get().strip()
        try:
            parse_action(action)
        except ValueError as error:
            self.status.set(str(error))
            return False
        key = selected[0]
        self.actions[key] = action
        self.table.set(key, 'action', action or 'Unassigned')
        self.status.set('Shortcut staged. Save settings to apply it.')
        return True

    def record(self, variable):
        recorder = ShortcutRecorder(self.window, variable.set)
        recorder.show()
        return recorder

    def commit(self):
        if not self.assign():
            return
        try:
            settings = dict(self.settings, output='shortcuts' if self.output.get() == SHORTCUTS else 'approximate',
                            stop=self.stop.get().strip(), shuttle_actions=dict(self.actions),
                            steps_per_turn={mode: int(variable.get()) for mode, variable in self.steps.items()})
            validate_settings(settings, parse_action)
        except (ValueError, TypeError) as error:
            messagebox.showerror('Invalid measured transport settings', str(error), parent=self.window)
            return
        if self.save(settings):
            self.window.destroy()
