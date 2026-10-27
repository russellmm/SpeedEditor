"""Run with xvfb-run -a .venv/bin/python tests/gui_smoke.py."""
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from speededitor.app import App
from speededitor.mapping import ROOT, load_profile

root = tk.Tk()
# Exercise the high-DPI case that used to clip text with a fixed row height.
if '--high-dpi' in sys.argv:
    root.tk.call('tk', 'scaling', 2.5)
with patch('speededitor.app.BatteryMonitor') as monitor:
    app = App(root)
    monitor.return_value.start.assert_called_once()
root.update()
assert len(app.table.get_children()) == 43
row_height = app.table.bbox('SMART_INSRT')[3]
assert row_height == app.table_font.metrics('linespace') + 2
assert app.table.column('id', 'width') >= app.table_font.measure('0x3C') + 12
with tempfile.TemporaryDirectory() as folder:
    app.path = Path(folder) / 'test.json'
    app.table.selection_set('CAM1')
    app.select_button()
    app.action.set('Ctrl+Shift+F1')
    app.apply_button()
    assert load_profile(app.path)['buttons']['CAM1'] == 'Ctrl+Shift+F1'
    app.wheel_vars['JOG'][0].set('Left')
    app.wheel_vars['JOG'][1].set('Right')
    app.wheel_vars['JOG'][2].set('64')
    app.apply_wheel()
    assert load_profile(app.path)['wheel']['JOG']['threshold'] == 64
app.profile_name.set('Resolve shortcuts')
app.switch_profile()
assert app.profile['buttons']['STOP_PLAY'] == 'Space'
app.profile_name.set('Desktop')
app.switch_profile()
app.worker.events.put(('keys', ({1}, [('SMART_INSRT', 'Ctrl+N')], 'JOG')))
app.worker.events.put(('battery', {'level': 82, 'charging': True}))
app.poll()
assert app.table.item('SMART_INSRT', 'tags') == ('held',)
assert '82%' in app.battery.get()
assert 'Charging' in app.battery.get()
app.worker.events.put(('battery', {'level': 81, 'charging': False}))
app.poll()
assert app.battery.get() == 'Battery: 81% • Not charging'
app.worker.events.put(('battery_unavailable', 'Battery: disconnected'))
app.poll()
assert app.battery.get() == 'Battery: disconnected'
app.worker.events.put(('keys', (set(), [], 'JOG')))
app.poll()
app.battery.set('Battery: — (UI test)')
root.update()
(ROOT / 'artifacts').mkdir(exist_ok=True)
subprocess.run(['import', '-window', str(root.winfo_id()), str(ROOT / 'artifacts/gui.png')], check=True)
root.destroy()
print('GUI smoke passed: 43 rows, editing/saving, profile switch, wheel settings, live events, screenshot.')
