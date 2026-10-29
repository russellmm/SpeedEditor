// REA/Frida observation of the Speed Editor only. No report mutation or commands.
'use strict';
const hid = Process.findModuleByName('hid.dll');
if (hid === null) throw new Error('Resolve has no loaded hid.dll');
const attributes = new NativeFunction(hid.getExportByName('HidD_GetAttributes'), 'uint8', ['pointer', 'pointer']);
const handles = new Map();
const pending = new Map();
let batch = [];
let total = 0;
const started = Date.now();
function selected(handle) {
    const key = handle.toString();
    if (!handles.has(key)) {
        const info = Memory.alloc(12);
        info.writeU32(12);
        const match = attributes(handle, info) !== 0 &&
            info.add(4).readU16() === 0x1edb && info.add(6).readU16() === 0xda0e;
        handles.set(key, match);
        if (match) send({kind: 'device', handle: key, vendor: 0x1edb, product: 0xda0e});
    }
    return handles.get(key);
}
function report(api, direction, buffer, length, handle, ok) {
    if (length < 1 || length > 64 || total >= 100000) return;
    const bytes = new Uint8Array(buffer.readByteArray(length));
    batch.push({t_ms: Date.now() - started, api, direction,
        handle: handle.toString(), ok,
        raw: Array.from(bytes, v => v.toString(16).padStart(2, '0')).join('')});
    total++;
    if (batch.length >= 100) flush();
}
function flush() {
    if (batch.length) { send({kind: 'reports', reports: batch}); batch = []; }
}
function hook(moduleName, name, callbacks) {
    const module = Process.findModuleByName(moduleName);
    if (module === null) return;
    const address = module.findExportByName(name);
    if (address !== null) Interceptor.attach(address, callbacks);
}
for (const name of ['HidD_GetFeature', 'HidD_GetInputReport', 'HidD_SetFeature', 'HidD_SetOutputReport']) {
    hook('hid.dll', name, {
        onEnter(args) {
            const error = this.lastError;
            this.selected = selected(args[0]);
            this.lastError = error;
            if (!this.selected) return;
            this.handle = args[0]; this.buffer = args[1]; this.length = args[2].toUInt32();
        },
        onLeave(result) {
            if (this.selected) report(name, name.includes('_Get') ? 'in' : 'out',
                this.buffer, this.length, this.handle, result.toInt32() !== 0);
        }
    });
}
hook('kernelbase.dll', 'ReadFile', {
    onEnter(args) {
        const error = this.lastError;
        this.selected = args[2].toUInt32() <= 64 && selected(args[0]);
        this.lastError = error;
        if (!this.selected) return;
        this.handle = args[0]; this.buffer = args[1]; this.length = args[2].toUInt32();
        this.count = args[3]; this.overlapped = args[4];
    },
    onLeave(result) {
        if (!this.selected) return;
        if (result.toInt32() !== 0) {
            const length = this.count.isNull() ? this.length : this.count.readU32();
            report('ReadFile', 'in', this.buffer, length, this.handle, true);
        } else if (this.lastError === 997 && !this.overlapped.isNull()) {
            pending.set(this.overlapped.toString(), {buffer: this.buffer, length: this.length, handle: this.handle});
        }
    }
});
for (const name of ['GetOverlappedResult', 'GetOverlappedResultEx']) {
    hook('kernelbase.dll', name, {
        onEnter(args) { this.overlapped = args[1]; this.count = args[2]; },
        onLeave(result) {
            const key = this.overlapped.toString();
            const item = pending.get(key);
            if (item && result.toInt32() !== 0) {
                report(name, 'in', item.buffer, this.count.readU32(), item.handle, true);
                pending.delete(key);
            }
        }
    });
}
hook('kernelbase.dll', 'WriteFile', {
    onEnter(args) {
        const error = this.lastError;
        this.selected = args[2].toUInt32() <= 64 && selected(args[0]);
        this.lastError = error;
        if (this.selected) report('WriteFile', 'out', args[1], args[2].toUInt32(), args[0], null);
    }
});
hook('kernelbase.dll', 'CloseHandle', {
    onEnter(args) { handles.delete(args[0].toString()); }
});
setInterval(flush, 250);
send({kind: 'ready', pid: Process.id, utc: new Date().toISOString(),
    modules: Process.enumerateModules().filter(m => /hid|bmd|panel/i.test(m.name)).map(m => m.name),
    limitations: 'HID API and ReadFile/WriteFile observation only. Existing pending reads and unhooked completion paths may be missed.'});
