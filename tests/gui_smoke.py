"""Render under Xvfb on Linux; use --headless for hidden Windows behavior checks."""
import os
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from speededitor.app import App, configure_display, DESKTOP_MODE, RESOLVE_MODE
from speededitor import __version__
from speededitor.mapping import ROOT, load_profile

configure_display()
root = tk.Tk()
headless = '--headless' in sys.argv
if headless:
    root.withdraw()
# Exercise the high-DPI case that used to clip text with a fixed row height.
if '--high-dpi' in sys.argv:
    root.tk.call('tk', 'scaling', 2.5)
with patch('speededitor.app.BatteryMonitor') as monitor:
    app = App(root)
    monitor.return_value.start.assert_called_once()
root.update()
assert app.version_label.cget('text') == f'v{__version__}'
assert f'v{__version__}' in root.title()
root.after(250, root.quit)
root.mainloop()
assert len(app.table.get_children()) == 43
row_height = (int(app.table.tk.call('ttk::style', 'lookup', 'Treeview', '-rowheight'))
              if headless else app.table.bbox('SMART_INSRT')[3])
assert row_height == app.table_font.metrics('linespace') + 2
assert app.table.column('id', 'width') >= app.table_font.measure('0x3C') + 12
with tempfile.TemporaryDirectory() as folder:
    app.path = Path(folder) / 'test.json'
    app.table.selection_set('CAM1')
    app.select_button()
    app.action.set('Ctrl+Shift+F1')
    app.apply_button()
    assert load_profile(app.path)['buttons']['CAM1'] == 'Ctrl+Shift+F1'
    saved = app.path.read_bytes()
    with patch('speededitor.app.ShortcutRecorder.show'):
        recorder = app.record_shortcut()
    assert recorder is not None
    assert recorder.use_button.instate(['disabled'])
    if not headless:
        recorder.show()
        root.update()
        recorder.capture.focus_force()
        recorder.capture.event_generate('<KeyPress>', keysym='Control_L')
        root.update()
        assert recorder.action is None
        recorder.capture.event_generate('<KeyPress>', keysym='comma', state=4)
        root.update()
        from PIL import ImageGrab
        ROOT.joinpath('artifacts').mkdir(exist_ok=True)
        ImageGrab.grab(bbox=(recorder.window.winfo_rootx(), recorder.window.winfo_rooty(),
                            recorder.window.winfo_rootx() + recorder.window.winfo_width(),
                            recorder.window.winfo_rooty() + recorder.window.winfo_height()),
                       **({'xdisplay': ''} if os.name != 'nt' else {})).save(ROOT / 'artifacts/shortcut-recorder.png')
    else:
        recorder.key_press(SimpleNamespace(keysym='Control_L', state=0))
        assert recorder.action is None
        recorder.key_press(SimpleNamespace(keysym='comma', state=4))
    assert recorder.preview.get() == 'Ctrl+Comma'
    assert app.path.read_bytes() == saved
    recorder.use()
    assert app.action.get() == 'Ctrl+Comma'
    assert app.path.read_bytes() == saved  # Recording alone does not save or update mapping.
    app.apply_button()
    assert load_profile(app.path)['buttons']['CAM1'] == 'Ctrl+Comma'
    app.action.set('Ctrl + ,')
    app.apply_button()
    assert load_profile(app.path)['buttons']['CAM1'] == 'Ctrl + ,'
    with patch('speededitor.app.ShortcutRecorder.show'):
        recorder = app.record_shortcut()
    recorder.key_press(SimpleNamespace(keysym='s', state=5))
    recorder.key_press(SimpleNamespace(keysym='Escape', state=0))
    assert app.action.get() == 'Ctrl + ,'
    app.wheel_vars['JOG'][0].set('Left')
    app.wheel_vars['JOG'][1].set('Right')
    app.wheel_vars['JOG'][2].set('64')
    assert app.wheel_behaviors['JOG'].get() == 'Standard'
    assert app.wheel_entries['JOG'][0].instate(['disabled'])
    app.wheel_behaviors['JOG'].set('Custom')
    app.update_wheel_fields('JOG')
    assert app.wheel_entries['JOG'][0].instate(['!disabled'])
    app.apply_wheel()
    assert load_profile(app.path)['wheel']['JOG']['threshold'] == 64
    assert load_profile(app.path)['wheel']['JOG']['behavior'] == 'custom'
    for mode in ('JOG', 'SCRL', 'SHTL'):
        app.wheel_behaviors[mode].set('Measured')
        app.update_wheel_fields(mode)
        assert app.wheel_entries[mode][2].instate(['disabled'])
    assert app.wheel_entries['JOG'][0].instate(['!disabled'])
    assert app.wheel_entries['SHTL'][0].instate(['disabled'])
    with patch('speededitor.app.MeasuredTransportEditor.show'):
        editor = app.edit_measured_transport()
    assert editor is not None
    with patch('speededitor.shortcut_capture.ShortcutRecorder.show'):
        recorder = editor.record(editor.stop)
    recorder.key_press(SimpleNamespace(keysym='k', state=4))
    recorder.use()
    assert editor.stop.get() == 'Ctrl+K'
    editor.steps['JOG'].set('30')
    saved = app.path.read_bytes()
    if not headless:
        editor.show()
        root.update()
        nested_recorder = editor.record(editor.stop)
        root.update()
        assert editor.window.grab_current() == nested_recorder.window
        nested_recorder.key_press(SimpleNamespace(keysym='Escape', state=0))
        assert editor.window.grab_current() == editor.window
        root.update()  # Repaint the parent after the nested recorder is destroyed.
        from PIL import ImageGrab
        editor_name = 'measured-transport-high-dpi.png' if '--high-dpi' in sys.argv else 'measured-transport.png'
        ImageGrab.grab(bbox=(editor.window.winfo_rootx(), editor.window.winfo_rooty(),
                            editor.window.winfo_rootx() + editor.window.winfo_width(),
                            editor.window.winfo_rooty() + editor.window.winfo_height()),
                       **({'xdisplay': ''} if os.name != 'nt' else {})).save(ROOT / 'artifacts' / editor_name)
    assert app.path.read_bytes() == saved  # Dialog edits are staged until Save settings.
    editor.commit()
    updated = load_profile(app.path)
    assert all(w['behavior'] == 'measured' for w in updated['wheel'].values())
    assert updated['measured_transport']['steps_per_turn']['JOG'] == 30
    assert updated['measured_transport']['stop'] == 'Ctrl+K'
    assert updated['measured_transport']['output'] == 'approximate'
    with patch('speededitor.app.MeasuredTransportEditor.show'):
        editor = app.edit_measured_transport()
    editor.steps['JOG'].set('70')
    editor.window.destroy()
    assert load_profile(app.path)['measured_transport']['steps_per_turn']['JOG'] == 30
    desktop_button = app.profile['buttons']['CAM1']
    desktop_wheel = dict(app.profile['wheel']['JOG'])
    app.connection_mode.set(RESOLVE_MODE)
    app.change_connection_mode()
    app.table.selection_set('CAM1')
    app.select_button()
    assert app.button_behavior.get() == 'Native'
    assert app.action_entry.instate(['disabled'])
    assert app.record_button.instate(['disabled'])
    assert app.record_shortcut() is None
    app.button_behavior.set('Shortcut')
    app.update_button_fields()
    assert app.record_button.instate(['!disabled'])
    app.action.set('Space')
    app.apply_button()
    assert load_profile(app.path)['resolve_buttons']['CAM1'] == 'Space'
    assert app.profile['buttons']['CAM1'] == desktop_button
    assert app.profile['wheel']['JOG'] == desktop_wheel
    assert app.wheel_entries['JOG'][2].instate(['disabled'])
    assert app.measured_setup.instate(['disabled'])
    assert app.edit_measured_transport() is None
    app.button_behavior.set('Disabled')
    app.apply_button()
    assert app.profile['resolve_buttons']['CAM1'] == ''
    app.button_behavior.set('Native')
    app.apply_button()
    assert 'CAM1' not in app.profile['resolve_buttons']
    app.table.selection_set('SHTL')
    app.select_button()
    assert app.button_behavior_picker.instate(['disabled'])
    assert app.action_entry.instate(['disabled'])
    assert app.record_button.instate(['disabled'])
    assert app.record_shortcut() is None
    with patch.object(app.worker, 'start') as start:
        app.start(False)
        start.assert_called_once_with(app.profile, False, native_resolve=True)
    app.worker.events.put(('stopped', None))
    app.poll()
    app.connection_mode.set(DESKTOP_MODE)
    app.change_connection_mode()
app.profile_name.set('Resolve shortcuts')
app.switch_profile()
assert app.profile['buttons']['STOP_PLAY'] == 'Space'
app.profile_name.set('Desktop')
app.switch_profile()
app.worker.events.put(('keys', ({1}, [('SMART_INSRT', 'Ctrl+N')], 'JOG')))
app.worker.events.put(('wheel', (401, 'Measured target +0.5× → approximate J/K/L level 1 (nominal 1×)', 0, 'SHTL')))
app.worker.events.put(('battery', {'level': 82, 'charging': True}))
app.poll()
assert 'Measured target +0.5×' in app.log.get('1.0', 'end')
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
app.profile_name.set('Resolve native wheel')
app.switch_profile()
assert app.connection_mode.get() == RESOLVE_MODE
assert app.profile['resolve_buttons'] == {}
app.table.selection_set('CAM9')
app.select_button()
assert app.button_behavior.get() == 'Native'
assert app.wheel_entries['SHTL'][2].instate(['disabled'])
app.battery.set('Battery: — (UI test)')
root.update()
(ROOT / 'artifacts').mkdir(exist_ok=True)
if not headless:
    from PIL import ImageGrab
    image_name = 'gui-windows' if os.name == 'nt' else 'gui'
    if '--high-dpi' in sys.argv:
        image_name += '-high-dpi'
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        user = ctypes.WinDLL('user32')
        user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user.GetAncestor.restype = wintypes.HWND
        screenshot = ImageGrab.grab(window=user.GetAncestor(root.winfo_id(), 2))
    else:
        screenshot = ImageGrab.grab(bbox=(root.winfo_rootx(), root.winfo_rooty(),
                                        root.winfo_rootx() + root.winfo_width(),
                                        root.winfo_rooty() + root.winfo_height()), xdisplay='')
    screenshot.save(ROOT / f'artifacts/{image_name}.png')
root.destroy()
print('GUI smoke passed: 43 rows, editing/saving, profile switch, wheel settings, live events; ' +
      ('hidden window, no screenshot.' if headless else 'screenshot.'))
