"""Offline, exact-scoped aggregation of existing fabric telemetry artifacts.

This collector never contacts devices and never replaces legacy artifacts.
"""
from copy import deepcopy
import json
import hashlib
from pathlib import Path

from controller.evidence_scope import build_node_resolver, resolve_record_scope
from controller.fabric_evidence_collector import categorize_metric


OUTPUT_NAME = 'fabric_evidence_scoped.json'


def _object(path):
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f'Expected JSON object: {path}')
    return data


def _path(value, folder):
    path = Path(value)
    if not path.is_absolute() and not path.exists():
        path = folder / path
    return path.resolve()


def build_scoped_report(root_cause, snapshot, anomalies, *, inventory, phase,
                        snapshot_path=None, anomaly_path=None, limit=50):
    """Aggregate only exact device/interface matches, preserving source scope."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError('Record limit must be a positive integer')
    nodes = snapshot.get('nodes', [])
    anomaly_rows = anomalies.get('anomalies', [])
    if not isinstance(nodes, list) or not isinstance(anomaly_rows, list):
        raise ValueError('Expected nodes/anomalies lists')
    resolve = build_node_resolver(inventory)
    targets = {}
    for target in root_cause.get('summary', {}).get('top_hotspots', []) or []:
        if not isinstance(target, dict):
            continue
        node = resolve(target.get('device'))
        interface = target.get('interface')
        if not node or not isinstance(interface, str) or not interface.strip():
            continue
        key = node, interface.strip()
        targets.setdefault(key, {
            'device': target.get('device'), 'interface': interface.strip(),
            'canonical_node': node, 'rx_port': target.get('rx_port'),
            'classification': target.get('classification'),
            'snapshot_records': [], 'snapshot_record_count': 0,
            'snapshot_summary': {}, 'anomalies': [], 'anomaly_count': 0,
            'anomaly_summary': {},
        })
    for ni, node in enumerate(nodes):
        if not isinstance(node, dict) or not isinstance(node.get('normalized_records', []), list):
            raise ValueError('Expected telemetry node object and normalized_records list')
        identity = node.get('node_name') or node.get('node')
        for ri, record in enumerate(node.get('normalized_records', [])):
            if not isinstance(record, dict):
                raise ValueError('Expected telemetry record object')
            key = resolve_record_scope(record, identity, resolve)
            if key not in targets:
                continue
            item = targets[key]
            category = categorize_metric(record.get('metric'))
            item['snapshot_record_count'] += 1
            item['snapshot_summary'][category] = item['snapshot_summary'].get(category, 0) + 1
            if len(item['snapshot_records']) < limit:
                item['snapshot_records'].append({
                    'node': identity, 'entity': record.get('entity'),
                    'metric': record.get('metric'), 'value': deepcopy(record.get('value')),
                    'category': category, 'phase': phase,
                    'source_phase': record.get('phase'),
                    'provenance': deepcopy(record),
                    'supporting_artifact': snapshot_path,
                    'json_pointer': f'/nodes/{ni}/normalized_records/{ri}',
                })
    for ai, anomaly in enumerate(anomaly_rows):
        if not isinstance(anomaly, dict):
            raise ValueError('Expected anomaly object')
        key = resolve_record_scope(anomaly, anomaly.get('node'), resolve)
        if key not in targets:
            continue
        item = targets[key]
        kind = anomaly.get('type') or 'unknown'
        item['anomaly_count'] += 1
        item['anomaly_summary'][kind] = item['anomaly_summary'].get(kind, 0) + 1
        if len(item['anomalies']) < limit:
            item['anomalies'].append({'observation': deepcopy(anomaly),
                                     'supporting_artifact': anomaly_path,
                                     'json_pointer': f'/anomalies/{ai}'})
    return {'collection_policy': 'exact_device_interface_v1', 'phase': phase,
            'record_limit_per_interface': limit, 'interfaces': list(targets.values()),
            'interpretation': 'Derived aggregation of existing telemetry; not independent corroboration or a health/recovery verdict.'}


def collect_campaign_fabric(case_summary_path, *, inventory):
    """Create a separate artifact, refusing to replace existing content or inputs."""
    case_path = Path(case_summary_path).resolve()
    summary = _object(case_path)
    files = summary.get('files') or {}
    if not isinstance(files, dict):
        raise ValueError('Case summary files must be an object')
    folder = case_path.parent
    explicit = files.get('root_cause_correlation')
    root_path = _path(explicit, folder) if isinstance(explicit, str) and explicit else (
        folder / 'traffic' / 'root_cause_correlation.json')
    if not explicit and (folder / 'root_cause_correlation.json').is_file():
        root_path = folder / 'root_cause_correlation.json'
    root_path = root_path.resolve()
    root = _object(root_path)
    output = folder / OUTPUT_NAME
    inputs = {case_path, root_path}
    phases, sources = {}, {}
    for phase in ('pre', 'running', 'post'):
        value = files.get(phase + '_telemetry')
        if not isinstance(value, str) or not value:
            sources[phase] = {'status': 'not_declared', 'path': None}
            continue
        path = _path(value, folder)
        inputs.add(path)
        if path == output.resolve():
            raise ValueError('Scoped output must not replace a source artifact')
        if not path.is_file():
            sources[phase] = {'status': 'missing', 'path': str(path)}
            continue
        try:
            snapshot = _object(path)
            phases[phase] = build_scoped_report(root, snapshot, {}, inventory=inventory,
                                                phase=phase, snapshot_path=str(path))
            sources[phase] = {'status': 'loaded', 'path': str(path)}
        except (ValueError, OSError) as error:
            sources[phase] = {'status': 'invalid', 'path': str(path), 'error': str(error)}
    if output.resolve() in inputs:
        raise ValueError('Scoped output must not replace a source artifact')
    input_hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in sorted(inputs) if path.is_file()}
    document = {
        'input_sha256': input_hashes,
        'missing_inputs': [str(path) for path in sorted(inputs) if not path.is_file()],
        'inventory_sha256': hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest(),
        'schema_version': '1.0', 'source_case_summary': str(case_path),
        'root_cause_artifact': str(root_path), 'source_availability': sources,
        'status': 'scoped_observations' if any(
            item['snapshot_record_count'] for phase in phases.values()
            for item in phase['interfaces']) else 'insufficient_scoped_coverage',
        'phases': phases,
        'limitations': ['This is derived telemetry aggregation, not independent fabric evidence.',
                        'Original fabric_evidence.json and legacy verdicts are preserved.',
                        'No raw validity, clock alignment, counter epoch or fault causality is inferred.'],
    }
    content = json.dumps(document, indent=2) + '\n'
    if output.exists():
        if output.read_text() == content:
            return str(output)
        raise FileExistsError(f'Refusing to replace existing scoped artifact: {output}')
    with output.open('x') as handle:
        handle.write(content)
    return str(output)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-summary', required=True)
    parser.add_argument('--inventory', required=True)
    args = parser.parse_args()
    print(collect_campaign_fabric(args.case_summary, inventory=_object(Path(args.inventory))))


def inspect_scoped_collection(case_summary_path, *, inventory=None):
    """Read supplemental coverage without adding an independent evidence source."""
    case_path = Path(case_summary_path).resolve()
    path = case_path.parent / OUTPUT_NAME
    result = {'status': 'missing', 'path': str(path)}
    if not path.is_file():
        return result
    try:
        data = _object(path)
        if data.get('source_case_summary') != str(case_path):
            raise ValueError('Scoped artifact belongs to a different case summary')
        if inventory is not None and data.get('inventory_sha256') != hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest():
            result.update(status='stale', error='Inventory scope changed since collection')
            return result
        hashes = data.get('input_sha256')
        if not isinstance(hashes, dict) or not hashes:
            raise ValueError('Missing scoped source fingerprints')
        for source in data.get('missing_inputs', []):
            if Path(source).exists():
                result.update(status='stale', error='Previously missing scoped input is now available: ' + source)
                return result
        for source, expected in hashes.items():
            source_path = Path(source)
            if not source_path.is_file() or hashlib.sha256(source_path.read_bytes()).hexdigest() != expected:
                result.update(status='stale', error='Scoped input changed or disappeared: ' + source)
                return result
        phases = data.get('phases')
        if not isinstance(phases, dict):
            raise ValueError('Expected scoped phases object')
        counts = {}
        for phase, report in phases.items():
            if report.get('collection_policy') != 'exact_device_interface_v1':
                raise ValueError('Unrecognized scoped collection policy')
            counts[phase] = sum(item['snapshot_record_count'] for item in report['interfaces'])
        result.update(status='loaded', observation_status=data.get('status'),
                      phase_record_counts=counts, limitations=data.get('limitations', []))
    except (ValueError, OSError, TypeError, KeyError, AttributeError) as error:
        result.update(status='invalid', error=str(error))
    return result


if __name__ == '__main__':
    main()
