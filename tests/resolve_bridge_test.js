'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const sourcePath = path.join(__dirname, '..', 'speededitor', 'resolve_bridge.js');
const {routeReport} = require(sourcePath);
function keys(...values) {
    const result = Array(13).fill(0); result[0] = 4;
    values.forEach((key, index) => { result[1 + index * 2] = key & 255; result[2 + index * 2] = key >> 8; });
    return result;
}
const rules = {'59': 'Space', '51': ''};
const wheel = [3, 3, 0, 16, 0, 0, 255, 0, 0, 0, 0, 0, 0];
assert.deepEqual(routeReport(wheel, new Set(), rules, true).bytes, wheel);
assert.deepEqual(routeReport(keys(59, 28), new Set(), rules, false).bytes, keys(59, 28));
let decision = routeReport(keys(59, 28), new Set(), rules, true);
assert.deepEqual(decision.bytes, keys(28));
assert.deepEqual(decision.actions, [{key: 59, action: 'Space'}]);
assert.deepEqual(routeReport(keys(59, 28), new Set([59, 28]), rules, true).actions, []);
assert.deepEqual(routeReport(keys(51), new Set(), rules, true).bytes, keys());
assert.deepEqual(routeReport(keys(51), new Set(), rules, true).actions, []);
assert.deepEqual(routeReport(keys(28, 29, 30), new Set(), {'28':'X','29':'X','30':'X'}, true).bytes, keys(28, 29, 30));
assert.deepEqual(routeReport(keys(0xffff, 59), new Set(), rules, true).bytes, keys(0xffff));
assert.deepEqual(routeReport(keys(), new Set([59]), rules, true).actions, []);

// Run the real hooks/RPC in a mocked Frida environment, using synthetic memory.
class Pointer {
    constructor(buffer, offset = 0) { this.buffer = buffer; this.offset = offset; }
    add(offset) { return new Pointer(this.buffer, this.offset + offset); }
    writeU32(value) { this.buffer.writeUInt32LE(value, this.offset); }
    readU32() { return this.buffer.readUInt32LE(this.offset); }
    readU16() { return this.buffer.readUInt16LE(this.offset); }
    readS32() { return this.buffer.readInt32LE(this.offset); }
    readByteArray(length) { return Uint8Array.from(this.buffer.subarray(this.offset, this.offset + length)).buffer; }
    writeByteArray(bytes) { this.buffer.set(new Uint8Array(bytes), this.offset); }
    isNull() { return false; }
    toString() { return 'ptr-' + this.buffer.length + '-' + this.offset; }
}
const hooks = {}, messages = [];
let clock = 1000, foreground = 47;
const context = {
    Process: {platform: 'windows', id: 47, mainModule: {name: 'Resolve.exe'},
        getModuleByName(name) { return {getExportByName: symbol => name + '!' + symbol,
                                      findExportByName: symbol => name + '!' + symbol}; }},
    Memory: {alloc: size => new Pointer(Buffer.alloc(size))},
    NativeFunction: function(address) {
        if (address.endsWith('HidD_GetAttributes')) return (_handle, info) => {
            info.buffer.writeUInt16LE(0x1edb, 4); info.buffer.writeUInt16LE(0xda0e, 6); return 1;
        };
        if (address.endsWith('GetForegroundWindow')) return () => ({});
        if (address.endsWith('GetWindowThreadProcessId')) return (_window, ptr) => { ptr.writeU32(foreground); return 1; };
        throw new Error(address);
    },
    Interceptor: {attach: (address, callbacks) => { hooks[address.split('!')[1]] = callbacks; }},
    rpc: {exports: {}}, send: message => messages.push(message), Date: {now: () => clock},
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(sourcePath, 'utf8'), context);
const rpc = context.rpc.exports;
const handle = {toString: () => 'device'};
const overlap = {toString: () => 'overlap', isNull: () => false};
function input(bytes, pending = false) {
    const buffer = new Pointer(Buffer.from(bytes));
    const count = new Pointer(Buffer.alloc(4)); count.writeU32(bytes.length);
    const invocation = {lastError: 0};
    hooks.ReadFile.onEnter.call(invocation, [handle, buffer, {toUInt32: () => bytes.length}, count, overlap]);
    invocation.lastError = pending ? 997 : 0;
    hooks.ReadFile.onLeave.call(invocation, {toInt32: () => pending ? 0 : 1});
    if (pending) {
        const completion = {lastError: 0};
        hooks.GetOverlappedResult.onEnter.call(completion, [handle, overlap, count]);
        hooks.GetOverlappedResult.onLeave.call(completion, {toInt32: () => 1});
    }
    return Array.from(buffer.buffer);
}
rpc.configure({rules, enabled: false});
assert.deepEqual(input(keys(59)), keys(59)); // Monitor remains byte-for-byte native.
input(keys());
rpc.configure({rules, enabled: true});
assert.deepEqual(input(wheel), wheel);
assert.deepEqual(input(keys(59, 29), true), keys(29)); // Real async completion hook.
let latest = messages.filter(m => m.kind === 'keys').at(-1);
assert.equal(latest.actions[0].action, 'Space');
input(keys());
foreground = 99;
assert.deepEqual(input(keys(59)), keys(59));
assert.equal(messages.filter(m => m.kind === 'keys').at(-1).actions.length, 0);
input(keys());
foreground = 47;
clock += 1600;
assert.deepEqual(input(keys(59)), keys(59)); // Lost host heartbeat restores native.
input(keys());
rpc.heartbeat();
assert.deepEqual(input(keys(59)), keys());
rpc.configure({rules: {}, enabled: false});
assert.deepEqual(input(keys(59)), keys(59));
assert.throws(() => rpc.configure({rules: {'28': 'Space'}, enabled: true}), /Invalid/);
console.log('Resolve routing passed: native wheel bytes, reserved modes, monitor, press edges, async read, focus, lease expiry and detach configuration.');
