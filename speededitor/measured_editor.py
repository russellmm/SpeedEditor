"""Desktop-only gains and stop shortcut; Resolve owns fractional playback."""
from copy import deepcopy
import tkinter as tk
from tkinter import messagebox, ttk

from .mapping import parse_action
from .measured_transport import validate_settings
from .shortcut_capture import ShortcutRecorder


class MeasuredTransportEditor:
    def __init__(self, parent, settings, save):
        self.settings = deepcopy(settings)
        self.save = save
        self.window = tk.Toplevel(parent)
        self.window.withdraw()
        self.window.title('Measured desktop transport — experimental')
        self.window.transient(parent)
        self.window.resizable(False, False)
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
        ttk.Label(body, text='Desktop SHTL uses the measured response with ordinary J/K/L transport.\n'
                            'Actual keyboard playback levels depend on the focused editor.\n'
                            'Continuous fractional-speed playback stays native to Resolve.').pack(anchor='w', pady=8)
        if settings['output'] == 'shortcuts':
            ttk.Label(body, text='This imported profile has custom speed shortcuts.\n'
                                'They are preserved when saving these gain settings.').pack(anchor='w', pady=5)
        buttons = ttk.Frame(body)
        buttons.pack(fill='x', pady=(12, 0))
        ttk.Button(buttons, text='Save settings', command=self.commit).pack(side='left')
        ttk.Button(buttons, text='Cancel', command=self.window.destroy).pack(side='right')

    def show(self):
        self.window.deiconify()
        self.window.grab_set()

    def record(self, variable):
        recorder = ShortcutRecorder(self.window, variable.set)
        recorder.show()
        return recorder

    def commit(self):
        try:
            settings = dict(self.settings, stop=self.stop.get().strip(),
                            steps_per_turn={mode: int(variable.get()) for mode, variable in self.steps.items()})
            validate_settings(settings, parse_action)
        except (ValueError, TypeError) as error:
            messagebox.showerror('Invalid measured transport settings', str(error), parent=self.window)
            return
        if self.save(settings):
            self.window.destroy()
