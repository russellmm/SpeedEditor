"""Summarize the saved REA/Frida HID reports, preserving mode and raw units."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct


def reports_from_bundle(bundle):
    # Status snapshots include earlier messages. Deduplicate identical reports
    # across snapshots; retain the complete original bundle as evidence.
    reports = {}
    evidence = []
    truncated = False
    for record in bundle['records']:
        result = record.get('normalized_result') or {}
        if record.get('operation') not in ('load_frida_script', 'frida_session_status'):
            continue
        evidence.append(record['evidence_id'])
        truncated |= bool(result.get('messages_truncated'))
        for message in result.get('messages', []):
            for report in (message.get('payload') or {}).get('reports', []):
                identity = (message.get('script_id'), report['t_ms'], report['api'],
                            report['direction'], report['raw'])
                reports[identity] = report
    return sorted(reports.values(), key=lambda r: r['t_ms']), evidence, truncated


def summarize(reports, start_ms=None, end_ms=None):
    mode = 'UNKNOWN'
    held = set()
    groups = defaultdict(list)
    events = []
    selected = []
    for report in reports:
        raw = bytes.fromhex(report['raw'])
        if report['direction'] == 'in' and raw[0] == 4 and len(raw) >= 13:
            keys = {key for key in struct.unpack_from('<6H', raw, 1) if key}
            for key in sorted(keys - held):
                mode = {0x1c: 'SHTL', 0x1d: 'JOG', 0x1e: 'SCRL'}.get(key, mode)
            held = keys
        if start_ms is not None and report['t_ms'] <= start_ms:
            continue
        if end_ms is not None and report['t_ms'] > end_ms:
            continue
        selected.append(report)
        if report['direction'] == 'in' and raw[0] == 3 and len(raw) >= 7:
            groups[(mode, raw[1])].append((report['t_ms'], struct.unpack_from('<i', raw, 2)[0]))
        elif report['direction'] == 'out' and raw[0] in (3, 4):
            events.append({'t_ms': report['t_ms'], 'kind': 'host_configuration',
                           'raw': report['raw'], 'api': report['api'], 'ok': report['ok']})
        elif report['direction'] == 'in' and raw[0] == 4:
            events.append({'t_ms': report['t_ms'], 'kind': 'buttons', 'mode': mode,
                           'held': sorted(held)})
    wheel = []
    for (mode, hardware_mode), values in groups.items():
        numbers = [v for _, v in values]
        wheel.append({'selected_mode': mode, 'hardware_mode': hardware_mode,
                      'reports': len(values), 'first_ms': values[0][0], 'last_ms': values[-1][0],
                      'min': min(numbers), 'max': max(numbers),
                      'sum': sum(numbers) if hardware_mode in (0, 2) else None,
                      'first_values': numbers[:8], 'last_values': numbers[-8:]})
    return {'reports': len(selected), 'wheel': wheel, 'events': events,
            'report_lengths': dict(Counter(len(bytes.fromhex(r['raw'])) for r in selected)),
            'limitations': 'Timestamps are API observation times. Sums apply only to relative modes 0/2. '
                           'Mode labels require an observed button press. No automatic timeline/frame-rate correlation.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--start-ms', type=int)
    parser.add_argument('--end-ms', type=int)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    source = args.bundle.read_bytes()
    reports, evidence, truncated = reports_from_bundle(json.loads(source))
    result = summarize(reports, args.start_ms, args.end_ms)
    result.update(source_sha256=hashlib.sha256(source).hexdigest(),
                  evidence_ids=evidence, messages_truncated=truncated)
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
