"""Compare a completed rebuild with its baseline using saved native outputs.

Checks targeted regressions and provenance. It does not infer semantic accuracy
from graph size or require every legitimate mention to have an edge.
"""
import argparse
from collections import Counter
from pathlib import Path
import re

from _common import read_json, write_json
from _sources import as_rows, load_tables
from _contracts import normalized
from serve import graph_payload


def stats(folder):
    tables = load_tables(folder)
    entities, edges = as_rows(tables['entities']), as_rows(tables['relationships'])
    degrees = Counter()
    for e in edges:
        degrees[e['source']] += 1
        degrees[e['target']] += 1
    return {'entities': len(entities), 'relationships': len(edges),
            'isolates': [e['title'] for e in entities if not degrees[e['title']]],
            'citation_nodes': [e['title'] for e in entities if re.search(r'\bet\s+al\.?\s*,?\s*\d{4}', e['title'], re.I)],
            'table_reference_nodes': [e['title'] for e in entities if re.match(r'(?i)^tab(?:le)?\.?\s*\d', e['title'])]}


def check(baseline, rebuilt):
    payload = graph_payload(rebuilt)
    nodes = {e['id']: e for e in payload['nodes']}
    assertions = [a for e in payload['edges'] for a in e['assertion_evidence']]
    vr = [e for e in payload['edges'] if any(normalized(nodes[i]['label']) == 'vr/ar'
                                             for i in [e['source'], e['target']])]
    vr_claims = [a for e in vr for a in e['assertion_evidence']]
    metric_dependencies = [a for a in assertions if a['kind'] in {'USES', 'DERIVED_FROM'}
                           and 'chamfer' in normalized(a['target'])
                           and any(k in normalized(a['source']) for k in ['mmd', 'cov', 'matching', 'coverage'])]
    initialization = [a for a in assertions if a['kind'] == 'INITIALIZED_FROM'
                      and 'cross-attention' in normalized(a['target'])]
    manifest = read_json(rebuilt / 'run.json')
    coverage = read_json(rebuilt / 'coverage.json')
    after = stats(rebuilt)
    gates = {'processing_complete': manifest['status'] == 'completed' and coverage['processing_complete'],
             'no_citation_nodes': not after['citation_nodes'],
             'no_table_reference_nodes': not after['table_reference_nodes'],
             'vr_ar_has_source_backed_application_edge': any(a['kind'] == 'APPLICABLE_TO' for a in vr_claims),
             'vr_ar_is_not_evaluation_dataset': not any(a['kind'] == 'EVALUATED_ON' for a in vr_claims),
             'metric_dependency_recovered': bool(metric_dependencies),
             'cross_attention_initialization_recovered': bool(initialization),
             'all_viewer_endpoints_resolve': all(e['source'] in nodes and e['target'] in nodes for e in payload['edges']),
             'all_native_edges_have_assertion_provenance': all(e['assertion_evidence'] for e in payload['edges'])}
    return {'baseline': stats(baseline), 'rebuilt': after, 'gates': gates,
            'targeted_gates_passed': all(gates.values()),
            'vr_ar_assertions': vr_claims, 'metric_dependencies': metric_dependencies,
            'cross_attention_initialization': initialization,
            'note': 'Targeted regression gates and provenance, not exhaustive semantic accuracy. Isolates are retained.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('rebuilt', type=Path)
    args = parser.parse_args()
    result = check(args.baseline, args.rebuilt)
    write_json(args.rebuilt / 'verification/rebuild_comparison.json', result)
    print('Before:', {k: len(v) if isinstance(v, list) else v for k, v in result['baseline'].items()})
    print('After:', {k: len(v) if isinstance(v, list) else v for k, v in result['rebuilt'].items()})
    print('Gates:', result['gates'])
    raise SystemExit(0 if result['targeted_gates_passed'] else 1)
