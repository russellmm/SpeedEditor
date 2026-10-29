/* Windows Resolve adapter. Default: native pass-through. No HID writes. */
'use strict';
const RESERVED = new Set([0x1c, 0x1d, 0x1e]);
const KNOWN = new Set([1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,
    26,27,28,29,30,31,34,37,38,43,44,45,46,47,48,49,51,52,53,54,55,56,57,58,59,60]);

function routeKeys(current, previous, rules, enabled) {
    const native = [], suppressed = [], actions = [];
    for (const key of current) {
        const mapped = enabled && !RESERVED.has(key) && Object.prototype.hasOwnProperty.call(rules, key);
        if (mapped) {
            suppressed.push(key);
            if (!previous.has(key) && rules[key]) actions.push({key, action: rules[key]});
        } else native.push(key);
    }
    return {native, suppressed, actions};
}

function routeReport(bytes, previous, rules, enabled) {
    if (bytes.length < 13 || bytes[0] !== 4) return {bytes: bytes.slice(), kind: 'other'};
    const current = [];
    for (let i = 1; i < 13; i += 2) {
        const key = bytes[i] | (bytes[i + 1] << 8);
        if (key && !current.includes(key)) current.push(key);
    }
    const decision = routeKeys(current, previous, rules, enabled);
    const result = bytes.slice();
    if (decision.suppressed.length) {
        for (let slot = 0; slot < 6; slot++) {
            const key = decision.native[slot] || 0;
            result[1 + slot * 2] = key & 255;
            result[2 + slot * 2] = key >> 8;
        }
    }
    return {bytes: result, kind: 'keys', held: current, ...decision};
}

if (typeof module !== 'undefined') module.exports = {routeKeys, routeReport};

if (typeof Process !== 'undefined') {
    if (Process.platform !== 'windows' || Process.mainModule.name.toLowerCase() !== 'resolve.exe')
        throw new Error('This adapter requires the running Windows Resolve.exe process');
    const hid = Process.getModuleByName('hid.dll');
    const kernel = Process.getModuleByName('kernelbase.dll');
    const user = Process.getModuleByName('user32.dll');
    const attributes = new NativeFunction(hid.getExportByName('HidD_GetAttributes'), 'uint8', ['pointer', 'pointer']);
    const foregroundWindow = new NativeFunction(user.getExportByName('GetForegroundWindow'), 'pointer', []);
    const windowPid = new NativeFunction(user.getExportByName('GetWindowThreadProcessId'), 'uint32', ['pointer', 'pointer']);
    const pidBuffer = Memory.alloc(4);
    const handles = new Map(), pending = new Map();
    let held = new Set(), rules = {}, enabled = false, leaseUntil = 0, armed = false;
    let keyReports = 0, wheelReports = 0, filteredReports = 0, lastWheel = 0;
    function selected(handle) {
        const key = handle.toString();
        if (!handles.has(key)) {
            const info = Memory.alloc(12);
            info.writeU32(12);
            const matched = attributes(handle, info) !== 0 && info.add(4).readU16() === 0x1edb && info.add(6).readU16() === 0xda0e;
            handles.set(key, matched);
        }
        return handles.get(key);
    }
    function focused() {
        windowPid(foregroundWindow(), pidBuffer);
        return pidBuffer.readU32() === Process.id;
    }
    function processReport(buffer, length) {
        if (length < 1 || length > 64) return;
        const original = new Uint8Array(buffer.readByteArray(length));
        if (!((original[0] === 3 && length >= 7) || (original[0] === 4 && length >= 13))) return;
        if (!armed) { armed = true; send({kind: 'armed', pid: Process.id}); }
        if (original[0] === 3 && length >= 7) {
            wheelReports++;
            if (Date.now() - lastWheel > 100) {
                lastWheel = Date.now();
                send({kind: 'wheel', hardware_mode: original[1], value: buffer.add(2).readS32()});
            }
            return; // Native wheel bytes are never rewritten.
        }
        if (original[0] !== 4 || length < 13) return;
        const active = enabled && armed && Date.now() < leaseUntil && focused();
        const decision = routeReport(Array.from(original), held, rules, active);
        try {
            if (decision.suppressed.length) {
                buffer.writeByteArray(decision.bytes);
                filteredReports++;
            }
        } catch (error) {
            enabled = false;
            try { buffer.writeByteArray(original); } catch (_) {}
            throw error;
        }
        held = new Set(decision.held);
        keyReports++;
        send({kind: 'keys', held: decision.held, native: decision.native,
              suppressed: decision.suppressed, actions: decision.actions,
              active, pid: Process.id});
    }
    function safely(buffer, length) {
        try { processReport(buffer, length); }
        catch (error) { enabled = false; send({kind: 'fault', error: String(error)}); }
    }
    Interceptor.attach(kernel.getExportByName('ReadFile'), {
        onEnter(args) {
            const error = this.lastError;
            this.selected = args[2].toUInt32() <= 64 && selected(args[0]);
            this.lastError = error;
            if (!this.selected) return;
            this.buffer = args[1]; this.length = args[2].toUInt32(); this.count = args[3];
            this.overlapped = args[4]; this.handle = args[0].toString();
        },
        onLeave(result) {
            if (!this.selected) return;
            if (result.toInt32() !== 0) safely(this.buffer, this.count.isNull() ? this.length : this.count.readU32());
            else if (this.lastError === 997 && !this.overlapped.isNull()) {
                if (pending.size > 64) { enabled = false; send({kind: 'fault', error: 'Too many outstanding HID reads'}); return; }
                pending.set(this.overlapped.toString(), {buffer: this.buffer, handle: this.handle});
            }
        }
    });
    for (const name of ['GetOverlappedResult', 'GetOverlappedResultEx']) {
        const address = kernel.findExportByName(name);
        if (address === null) continue;
        Interceptor.attach(address, {
            onEnter(args) { this.handle = args[0].toString(); this.overlapped = args[1]; this.count = args[2]; },
            onLeave(result) {
                const key = this.overlapped.toString(), item = pending.get(key);
                if (!item || item.handle !== this.handle) return;
                if (result.toInt32() !== 0) {
                    pending.delete(key);
                    safely(item.buffer, this.count.readU32());
                } else if (this.lastError !== 996 && this.lastError !== 258) pending.delete(key);
            }
        });
    }
    Interceptor.attach(hid.getExportByName('HidD_GetInputReport'), {
        onEnter(args) {
            const error = this.lastError;
            this.selected = args[2].toUInt32() <= 64 && selected(args[0]);
            this.lastError = error;
            if (this.selected) { this.buffer = args[1]; this.length = args[2].toUInt32(); }
        },
        onLeave(result) {
            if (this.selected && result.toInt32() !== 0) safely(this.buffer, this.length);
        }
    });
    Interceptor.attach(kernel.getExportByName('CloseHandle'), {
        onEnter(args) {
            const key = args[0].toString();
            if (handles.get(key)) {
                for (const [id, item] of pending) if (item.handle === key) pending.delete(id);
            }
            handles.delete(key);
        }
    });
    rpc.exports = {
        configure(config) {
            const candidate = {};
            for (const [key, action] of Object.entries(config.rules || {})) {
                const code = Number(key);
                if (!KNOWN.has(code) || RESERVED.has(code) || typeof action !== 'string' || action.length > 256)
                    throw new Error('Invalid Resolve button override');
                candidate[code] = action;
            }
            rules = candidate;
            enabled = config.enabled === true;
            leaseUntil = Date.now() + 1500;
            return {pid: Process.id, armed, enabled};
        },
        heartbeat() {
            leaseUntil = Date.now() + 1500;
            return {pid: Process.id, armed, enabled, keyReports, wheelReports, filteredReports};
        },
        // Pure synthetic reports: verifies routing without reading/writing a device.
        inspectreport(bytes, previous, testRules, active) {
            return routeReport(bytes, new Set(previous), testRules, active);
        }
    };
    send({kind: 'ready', pid: Process.id, active: false, protocol: 1});
}
