"""Read saved RoCE snapshots without changing legacy analysis artifacts."""
import json
from pathlib import Path

from controller.rocev2_deep_inspector import compare_pre_post, flow_key


def build_roce_qualification(case_path, files):
    folder = Path(case_path).resolve().parent
    sources, snapshots = {}, {}
    for phase in ('pre', 'post'):
        explicit = files.get('rocev2_' + phase)
        path = Path(explicit) if isinstance(explicit, str) and explicit else (
            folder / 'traffic' / f'rocev2_{phase}_ixia_rocev2_flow_stats.json')
        if not path.is_absolute() and not path.exists():
            path = folder / path
        path = path.resolve()
        entry = {'path': str(path), 'status': 'missing'}
        if path.is_file():
            try:
                data = json.loads(path.read_text())
                if not isinstance(data, dict) or not isinstance(data.get('normalized_rows'), list):
                    raise ValueError('Expected normalized_rows list')
                if any(not isinstance(row, dict) for row in data['normalized_rows']):
                    raise ValueError('Expected object rows')
                snapshots[phase] = data
                entry.update(status='loaded', row_count=len(data['normalized_rows']),
                             session_id=data.get('session_id'), view_name=data.get('view_name'),
                             view_found=data.get('view_found'), view_mismatch=data.get('view_mismatch'))
            except (OSError, ValueError) as error:
                entry.update(status='invalid', error=str(error))
        sources[phase] = entry
    comparisons = []
    if len(snapshots) == 2:
        pre, post = (snapshots[phase]['normalized_rows'] for phase in ('pre', 'post'))
        indices = []
        for rows in (pre, post):
            mapping = {}
            for index, row in enumerate(rows):
                mapping.setdefault(flow_key(row), []).append(index)
            indices.append(mapping)
        for row in compare_pre_post(pre, post):
            key = flow_key(row)
            comparisons.append({
                'flow_identity': {field: row.get(field) for field in
                                  ('flow_name', 'tx_port', 'rx_port', 'src_qp', 'dest_qp')},
                'source_row_indices': {'pre': indices[0].get(key, []),
                                       'post': indices[1].get(key, [])},
                'snapshot_differences': {
                    metric: {suffix: row.get(f'{metric}_{suffix}')
                             for suffix in ('pre', 'post', 'increase')}
                    for metric in ('frames_delta', 'retx', 'seqerror', 'message_failed', 'ecn')},
                'comparison_coverage': row['comparison_coverage'],
            })
    return {
        'status': 'snapshot_differences_only' if comparisons else 'insufficient_snapshot_coverage',
        'source_availability': sources, 'flow_count': len(comparisons), 'flows': comparisons,
        'limitations': ['Snapshot differences are not qualified interval increments; source validity, reset epochs and aligned windows remain unverified.',
                        'Frame discrepancy is not established packet loss, including when RX exceeds TX.',
                        'Duplicate rows are not independent evidence. Session identity does not prove counter continuity.',
                        'Traffic path and event causality require independent validation; delayed recovery is not established.'],
    }
