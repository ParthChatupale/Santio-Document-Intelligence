"""Offline isolation diagnosis. Never edits graph tables or calls a model.

Replays saved extraction responses against the existing contract. A second,
explicitly counterfactual replay tests declarations from the SAME source's
verified initial pass. Passing that replay is NOT semantic approval.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from _common import read_json, write_json
from _contracts import GraphRecords, native_messages, normalized, project, source_text
from _sources import as_rows, load_tables, source_ledger


MISSING_ENDPOINT = "Relationship endpoint not declared in this extraction"


def record_key(record):
    return json.dumps(record, sort_keys=True, ensure_ascii=False)


def accepted_entities(records, source):
    """Replay entity checks and the contract's documented Dataset suffix alias."""
    _, audit = project(GraphRecords(entities=records.entities, relationships=[]), source)
    rejected = {normalized(w['record']['name']) for w in audit['withheld_records']}
    accepted = []
    for entity in records.entities:
        entity = entity.model_copy(deep=True)
        entity.name = audit['entity_name_aliases'].get(entity.name, entity.name)
        if normalized(entity.name) not in rejected:
            accepted.append(entity)
    return accepted


def replay_with_prior_declarations(current, previous, source):
    """An audit experiment, not a graph repair or global endpoint lookup.

    Both records must belong to an already matched initial/continuation pair.
    Rejected initial declarations never enter the scope. Conflicting types or
    duplicate current identities cannot authorize a recovered relationship.
    """
    prior = accepted_entities(previous, source)
    current_valid = accepted_entities(current, source)
    raw_keys = {normalized(e.name) for e in current.entities}
    present = {normalized(e.name): e for e in current_valid}
    conflicts = {normalized(e.name) for e in prior if normalized(e.name) in present
                 and present[normalized(e.name)].type != e.type}
    combined = GraphRecords(entities=current.entities + [e for e in prior
                            if normalized(e.name) not in raw_keys],
                            relationships=current.relationships)
    _, audit = project(combined, source)
    checks_passed = [r for r in audit['relationship_evidence']
                     if not {normalized(r['source']), normalized(r['target'])} & conflicts]
    return checks_passed, sorted(conflicts)


def verify_viewer(entities, relationships, payload):
    """Check identity AND endpoint mapping, not just matching aggregate counts."""
    native_nodes = {e['id']: e for e in entities}
    native_edges = {e['id']: e for e in relationships}
    nodes = {e['id']: e for e in payload['nodes']}
    edges = {e['id']: e for e in payload['edges']}
    wrong = []
    for ident in native_edges.keys() & edges.keys():
        edge, original = edges[ident], native_edges[ident]
        if (nodes.get(edge['source'], {}).get('label') != original['source']
                or nodes.get(edge['target'], {}).get('label') != original['target']):
            wrong.append(ident)
    return {'native_nodes': len(entities), 'native_edges': len(relationships),
            'viewer_nodes': len(payload['nodes']), 'viewer_edges': len(payload['edges']),
            'missing_node_ids': sorted(native_nodes.keys() - nodes.keys()),
            'extra_node_ids': sorted(nodes.keys() - native_nodes.keys()),
            'missing_edge_ids': sorted(native_edges.keys() - edges.keys()),
            'extra_edge_ids': sorted(edges.keys() - native_edges.keys()),
            'wrong_endpoint_mappings': sorted(wrong),
            'duplicate_viewer_node_ids': len(payload['nodes']) - len(nodes),
            'duplicate_viewer_edge_ids': len(payload['edges']) - len(edges)}


def fingerprints(run):
    """Input/output evidence remains byte-for-byte intact during this audit."""
    folders = ['input', 'output', 'requests', 'validated_extractions', 'prompts']
    paths = [p for name in folders for p in (run / name).rglob('*') if p.is_file()]
    paths += [run / name for name in ['source_map.json', 'run.json', 'model_calls.json',
                                      'settings.yaml', 'coverage.json']]
    return {str(p.relative_to(run)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths) if p.is_file()}


def inspect(run, viewer=None):
    run = Path(run).resolve(strict=True)
    tables = load_tables(run)
    entities, relationships = as_rows(tables['entities']), as_rows(tables['relationships'])
    sources, ledger = source_ledger(run, tables)
    names = {normalized(e['title']): e for e in entities}
    degree = Counter()
    for edge in relationships:
        degree[normalized(edge['source'])] += 1
        degree[normalized(edge['target'])] += 1
    originals = {tuple(sorted([normalized(e['source']), normalized(e['target'])]))
                 for e in relationships}
    units = read_json(run / 'coverage.json')['units']
    initial_keys = {u['successful_extraction_request']: u for u in units}
    initial_by_source = defaultdict(list)
    for key, unit in initial_keys.items():
        request = read_json(run / 'requests' / (key + '.json'))
        initial_by_source[source_text(request['messages'])].append((key, unit))
    successful = {c['request_hash'] for c in read_json(run / 'model_calls.json')['completion_calls']
                  if c['status'] in {'completed', 'cache_hit'}}
    occurrences, rejections, phase_reasons = Counter(), Counter(), Counter()
    accepted_by_name, withheld_by_name = defaultdict(list), defaultdict(list)
    replay_failures, skipped, candidates = [], [], []
    type_conflicts = []
    response_count = 0
    for path in sorted((run / 'validated_extractions').glob('*.json')):
        if path.stem not in successful:
            skipped.append({'request': path.stem, 'reason': 'Not a successful saved request'})
            continue
        saved = read_json(path)
        request = read_json(run / 'requests' / path.name)
        messages = native_messages(request['messages'])
        source = source_text(messages)
        matches = initial_by_source.get(source, [])
        if path.stem in initial_keys:
            matches = [(path.stem, initial_keys[path.stem])]
            phase = 'initial'
        elif len(messages) == 3:
            matches = [(key, unit) for key, unit in matches
                       if json.loads(messages[1]['content']) ==
                       read_json(run / 'validated_extractions' / (key + '.json'))['records']]
            phase = 'additional'
        else:
            matches = []
            phase = 'unmatched'
        if len(matches) != 1:
            skipped.append({'request': path.stem, 'reason': 'Initial/source/history match not unique'})
            continue
        initial_key, unit = matches[0]
        records = GraphRecords.model_validate(saved['records'])
        canonical, audit = project(records, source)
        response_count += 1
        if canonical != saved['canonical_tuples']:
            replay_failures.append(path.stem)
        occurrences.update({k: audit[k] for k in ['raw_entities', 'raw_relationships',
                                                'entities', 'relationships']})
        provenance = {'request_hash': path.stem, 'phase': phase,
                      'unit_id': unit['id'], 'source_ids': unit['source_ids']}
        for entity in accepted_entities(records, source):
            accepted_by_name[normalized(entity.name)].append({**provenance, **entity.model_dump()})
        checks_passed = set()
        if phase == 'additional':
            prior = GraphRecords.model_validate(read_json(run / 'validated_extractions' /
                                                          (initial_key + '.json'))['records'])
            changed, conflicts = replay_with_prior_declarations(records, prior, source)
            checks_passed = {record_key(r) for r in changed}
            if conflicts:
                type_conflicts.append({**provenance, 'identities': conflicts})
        for withheld in audit['withheld_records']:
            rejections[withheld['reason']] += 1
            phase_reasons[(phase, withheld['reason'])] += 1
            if withheld['record_type'] != 'relationship':
                continue
            relation = withheld['record']
            row = {**provenance, **relation, 'reason': withheld['reason']}
            for key in {normalized(relation['source']), normalized(relation['target'])}:
                withheld_by_name[key].append(row)
            if withheld['reason'] == MISSING_ENDPOINT and record_key(relation) in checks_passed:
                pair = tuple(sorted([normalized(relation['source']), normalized(relation['target'])]))
                candidates.append({**row, 'pair_already_in_graph': pair in originals,
                                   'both_endpoints_in_native_graph': all(k in names for k in pair),
                                   'semantic_status': 'NOT_VERIFIED', 'promoted_to_graph': False})
    isolates = []
    for entity in entities:
        key = normalized(entity['title'])
        if degree[key]:
            continue
        ids = sorted(ledger.get(('entities', str(entity['id'])), set()))
        matching = [r for r in candidates if key in {normalized(r['source']), normalized(r['target'])}]
        isolates.append({'id': entity['id'], 'name': entity['title'], 'type': entity['type'],
                         'description': entity['description'], 'source_ids': ids,
                         'pages': sorted({p for ident in ids for p in sources[ident]['pages']}),
                         'extraction_occurrences': accepted_by_name[key],
                         'withheld_relationship_occurrences': withheld_by_name[key],
                         'scope_replay_candidate_occurrences': len(matching),
                         'citation_like_name': bool(re.search(r'\bet al\.', entity['title'], re.I)),
                         'structure_like_name': bool(re.match(r'^(?:Tab\.|Table|Appendix|Figure)\s', entity['title'], re.I))})
    pairs = {tuple(sorted([normalized(r['source']), normalized(r['target'])])) for r in candidates}
    new_pairs = pairs - originals
    candidate_isolates = {normalized(e['name']) for e in isolates
                          if e['scope_replay_candidate_occurrences']}
    return {'run_directory': str(run), 'scope': 'Offline diagnosis; NO graph repairs or semantic approvals',
            'native_entities': len(entities), 'native_relationships': len(relationships),
            'isolated_entities': len(isolates), 'isolate_types': dict(Counter(e['type'] for e in isolates)),
            'citation_like_isolates': sum(e['citation_like_name'] for e in isolates),
            'structure_like_isolates': sum(e['structure_like_name'] for e in isolates),
            'isolates_without_any_exact_name_relationship_candidate': sum(
                not e['withheld_relationship_occurrences'] for e in isolates),
            'isolates_per_source': dict(Counter(i for e in isolates for i in e['source_ids'])),
            'responses_replayed': response_count, 'skipped_responses': skipped,
            'canonical_replay_mismatches': replay_failures,
            'occurrences': dict(occurrences), 'rejection_reasons': dict(rejections),
            'rejections_by_phase': [{'phase': phase, 'reason': reason, 'count': count}
                                    for (phase, reason), count in sorted(phase_reasons.items())],
            'same_source_declaration_experiment': {
                'checks_passing_occurrences': len(candidates), 'distinct_undirected_pairs': len(pairs),
                'pairs_absent_from_native_graph': len(new_pairs),
                'affected_isolates': sorted(candidate_isolates), 'type_conflicts': type_conflicts,
                'semantic_entailment_verified': False, 'graph_modified': False},
            'viewer_comparison': verify_viewer(entities, relationships, viewer) if viewer else None,
            'sources': {i: sources[i] for e in isolates for i in e['source_ids']},
            'isolates': sorted(isolates, key=lambda e: e['name']),
            'scope_replay_candidates': candidates}


def markdown(report):
    experiment = report['same_source_declaration_experiment']
    lines = ['# Isolated-node extraction audit', '',
             'Offline replay of saved model output. No model calls or graph edits.', '',
             f"- Native graph: {report['native_entities']} entities / {report['native_relationships']} edges.",
             f"- Actual isolated entities: {report['isolated_entities']}.",
             f"- Citation-like isolates: {report['citation_like_isolates']}; structure-like: {report['structure_like_isolates']}.",
             f"- Matched responses replayed: {report['responses_replayed']}; replay differences: {len(report['canonical_replay_mismatches'])}.",
             f"- Same-source prior-declaration experiment: {experiment['checks_passing_occurrences']} candidate occurrences pass existing checks; semantic correctness is NOT established.",
             f"- Candidate pairs absent from current graph: {experiment['pairs_absent_from_native_graph']}; isolates touched: {len(experiment['affected_isolates'])}.", '',
             'Counts of occurrences, candidate pairs and true scientific facts are different quantities.', '',
             '| Isolated entity | Type | PDF pages | Rejected candidate occurrences | Declaration experiment candidates |',
             '| --- | --- | --- | ---: | ---: |']
    for node in report['isolates']:
        name = node['name'].replace('|', '\\|')
        lines.append(f"| {name} | {node['type']} | {', '.join(map(str, node['pages']))} | "
                     f"{len(node['withheld_relationship_occurrences'])} | {node['scope_replay_candidate_occurrences']} |")
    lines += ['', 'Full request hashes, quotations, rejection reasons, source text and replay candidates are in audit.json.',
              'The source-backed interpretation and repair priorities are documented separately in ISOLATION_AUDIT.md.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--viewer-json', type=Path,
                        help='Optional saved /api/graph payload; no network requests are made')
    args = parser.parse_args()
    run = args.run.resolve(strict=True)
    target = args.output.resolve()
    if target == run or run in target.parents:
        raise ValueError('Keep diagnostic output outside the original run.')
    if target.exists():
        raise ValueError('Choose a new diagnostic output directory.')
    before = fingerprints(run)
    result = inspect(run, read_json(args.viewer_json) if args.viewer_json else None)
    after = fingerprints(run)
    result['integrity'] = {'files_checked': len(before), 'unchanged': before == after,
                           'sha256_before': before, 'sha256_after': after}
    write_json(target / 'audit.json', result)
    (target / 'isolate_inventory.md').write_text(markdown(result), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['native_entities', 'native_relationships',
          'isolated_entities', 'responses_replayed', 'citation_like_isolates', 'viewer_comparison']}, indent=2))
    print(json.dumps(result['same_source_declaration_experiment'], indent=2))
    print('Evidence unchanged:', result['integrity']['unchanged'])
    print('Report:', target / 'audit.json')
    if before != after or result['canonical_replay_mismatches'] or result['skipped_responses']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
