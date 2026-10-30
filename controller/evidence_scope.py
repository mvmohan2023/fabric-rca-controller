"""Exact inventory-backed evidence scope, shared by collectors and RCA replay."""
from collections import defaultdict


def build_node_resolver(inventory):
    names = defaultdict(set)
    for row in inventory.get('nodes', []):
        if not isinstance(row, dict):
            continue
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


def resolve_record_scope(record, node, resolve):
    """Return device/interface identity only when supplied identities agree."""
    identity = resolve(node)
    if identity is None:
        return None
    if record.get('node') and resolve(record['node']) != identity:
        return None
    entity = record.get('entity')
    if entity is not None and not isinstance(entity, str):
        return None
    entity_interface = (entity or '').split(':queue', 1)[0].split(':pg', 1)[0]
    labels = record.get('labels') or {}
    if not isinstance(labels, dict):
        return None
    interface = labels.get('interface') or entity_interface
    if not isinstance(interface, str) or not interface.strip():
        return None
    if entity_interface and interface != entity_interface:
        return None
    return identity, interface
