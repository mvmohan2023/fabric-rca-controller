"""Derived coverage from saved telemetry; never an independent evidence source."""
from collections import defaultdict
from pathlib import Path
import json


def _node_resolver(inventory):
    names = defaultdict(set)
    for row in inventory.get('nodes', []):
        device = str(row.get('device') or '').strip().lower()
        if not device:
            continue
        for field in ('device', 'alias', 'role', 'hostname'):
            name = str(row.get(field) or '').strip().lower()
            if name:
                names[name].add(device)
    def resolve(value):
        name = str(value or '').strip().lower()
        matches = names.get(name, {name} if name else set())
        return next(iter(matches)) if len(matches) == 1 else None
    return resolve


def build_fabric_replay(case_path, files, root_cause, inventory):
    """Match exact device/interface pairs; retain zero observations verbatim."""
    resolve = _node_resolver(inventory)
    targets = {}
    for row in (root_cause or {}).get('summary', {}).get('top_hotspots', []) or []:
        if not isinstance(row, dict):
            continue
        node, interface = resolve(row.get('device')), row.get('interface')
        if node and isinstance(interface, str) and interface.strip():
            targets[(node, interface.strip())] = {'device': row.get('device'),
                                                 'interface': interface.strip()}
    sources, phases = {}, {}
    folder = Path(case_path).resolve().parent
    for phase in ('pre', 'running', 'post'):
        explicit = files.get(phase + '_telemetry')
        entry = {'status': 'not_declared', 'path': None}
        rows = {}
        if isinstance(explicit, str) and explicit:
            path = Path(explicit)
            if not path.is_absolute() and not path.exists():
                path = folder / path
            path = path.resolve()
            entry = {'status': 'missing', 'path': str(path)}
            if path.is_file():
                try:
                    data = json.loads(path.read_text())
                    if not isinstance(data, dict) or not isinstance(data.get('nodes'), list):
                        raise ValueError('Expected telemetry nodes list')
                    entry['status'] = 'loaded'
                    for ni, node in enumerate(data['nodes']):
                        if not isinstance(node, dict):
                            continue
                        identity = resolve(node.get('node_name') or node.get('node'))
                        records = node.get('normalized_records') or []
                        if not isinstance(records, list):
                            continue
                        for ri, record in enumerate(records):
                            if not isinstance(record, dict):
                                continue
                            entity = str(record.get('entity') or '')
                            entity_interface = entity.split(':queue', 1)[0].split(':pg', 1)[0]
                            labels = record.get('labels') or {}
                            interface = labels.get('interface') if isinstance(labels, dict) else None
                            interface = interface or entity_interface
                            # Conflicting labels/entity identities cannot establish scope.
                            if entity_interface and interface != entity_interface:
                                continue
                            key = (identity, interface)
                            if key not in targets:
                                continue
                            if record.get('node') and resolve(record['node']) != identity:
                                continue
                            bucket = rows.setdefault(key, {'total_records': 0, 'records': []})
                            bucket['total_records'] += 1
                            if len(bucket['records']) < 50:
                                bucket['records'].append({
                                    'json_pointer': f'/nodes/{ni}/normalized_records/{ri}',
                                    'entity': record.get('entity'), 'metric': record.get('metric'),
                                    'value': record.get('value'), 'labels': record.get('labels'),
                                    'measurement_provenance': record.get('measurement_provenance'),
                                })
                except (OSError, ValueError) as error:
                    entry.update(status='invalid', error=str(error))
        sources[phase] = entry
        phases[phase] = rows
    interfaces = []
    for key, target in targets.items():
        interfaces.append({**target, 'canonical_node': key[0], 'phases': {
            phase: {**phases[phase].get(key, {'total_records': 0, 'records': []}),
                    'supporting_artifact': sources[phase]['path']}
            for phase in phases}})
    count = sum(row['phases'][phase]['total_records'] for row in interfaces for phase in phases)
    return {
        'status': 'derived_snapshot_coverage' if count else 'insufficient_scoped_coverage',
        'source_availability': sources, 'target_count': len(targets),
        'matched_record_count': count, 'interfaces': interfaces,
        'limitations': ['Replay is derived from existing normalized telemetry, not an independent collector or evidence domain; original fabric source availability is unchanged.',
                        'Exact inventory-resolved device and interface matching is required; ambiguous inventory names are excluded.',
                        'At most 50 records per interface per phase are displayed; total_records reports full matching coverage.',
                        'Recorded zeros do not establish raw measurement validity. No health, recovery, aligned window or counter epoch is inferred.'],
    }
