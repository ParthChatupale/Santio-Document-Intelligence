"""Offline accounting of validated responses and native graph provenance.

This checks format consumption, quoted-source matching and source coverage.
It deliberately does not turn those checks into a semantic accuracy score.
"""
import argparse
from collections import Counter
from pathlib import Path

from _common import read_json, write_json
from _contracts import GraphRecords, project, native_messages


def replay_native(run, coverage, calls, actual_relationships):
    """Replay the actual initial+gleaning concatenation and native graph merging."""
    from graphrag.index.operations.extract_graph.graph_extractor import GraphExtractor
    from graphrag.index.operations.extract_graph.extract_graph import _merge_entities, _merge_relationships
    from graphrag.index.operations.extract_graph.utils import filter_orphan_relationships
    parser = GraphExtractor.__new__(GraphExtractor)
    accepted = {c['request_hash'] for c in calls if c['status'] in {'completed', 'cache_hit'}}
    requests = {key: read_json(run / 'requests' / (key + '.json')) for key in accepted
                if (run / 'validated_extractions' / (key + '.json')).exists()}
    requests = {key: {**value, 'messages': native_messages(value['messages'])} for key, value in requests.items()}
    entity_frames, relationship_frames, units, errors = [], [], [], []
    for unit in coverage.get('units', []):
        key = unit.get('successful_extraction_request')
        if key not in requests:
            errors.append({'unit_id': unit['id'], 'error': 'No validated initial request'})
            continue
        initial = read_json(run / 'validated_extractions' / (key + '.json'))
        first_message = requests[key]['messages'][0]
        def same_history(request):
            history = request['messages'][1].get('content', '')
            try:
                return __import__('json').loads(history) == initial['records']
            except ValueError:
                return history == initial['canonical_tuples']
        glean_keys = [k for k, request in requests.items() if len(request['messages']) == 3
                      and request['messages'][0] == first_message and same_history(request)]
        if len(glean_keys) != 1:
            errors.append({'unit_id': unit['id'], 'error': 'Expected one native additional extraction pass',
                           'matching_passes': glean_keys})
        responses = [initial] + [read_json(run / 'validated_extractions' / (k + '.json')) for k in glean_keys]
        combined = ''.join(r['canonical_tuples'] for r in responses)
        entities, relations = parser._process_result(combined, unit['id'], '<|>', '##')
        expected_entities = sum(r['entities'] for r in responses)
        expected_relations = sum(r['relationships'] for r in responses)
        if len(entities) != expected_entities or len(relations) != expected_relations:
            errors.append({'unit_id': unit['id'], 'error': 'Native combined-pass record loss'})
        entity_frames.append(entities)
        relationship_frames.append(relations)
        units.append({'unit_id': unit['id'], 'initial_request': key, 'additional_requests': glean_keys,
                      'expected_entities': expected_entities, 'parsed_entities': len(entities),
                      'expected_relationships': expected_relations, 'parsed_relationships': len(relations)})
    if not units:
        return {'status': 'not_available', 'errors': errors}
    merged_entities = _merge_entities(entity_frames)
    merged_relations = _merge_relationships(relationship_frames)
    filtered = filter_orphan_relationships(merged_relations, merged_entities)
    expected = {(r['source'], r['target']): r['weight'] for r in filtered.to_dict('records')}
    actual = {(r['source'], r['target']): r['weight'] for r in actual_relationships}
    return {'status': 'replayed', 'units_replayed': len(units), 'errors': errors,
            'accepted_entity_occurrences': sum(u['expected_entities'] for u in units),
            'native_parsed_entity_occurrences': sum(u['parsed_entities'] for u in units),
            'accepted_relationship_occurrences': sum(u['expected_relationships'] for u in units),
            'native_parsed_relationship_occurrences': sum(u['parsed_relationships'] for u in units),
            'native_orphan_pairs_dropped': len(merged_relations) - len(filtered),
            'native_relationship_pair_set_exact_match': set(expected) == set(actual),
            'native_relationship_weights_exact_match': expected == actual,
            'units': units}


def inspect(run):
    from _sources import as_rows, load_tables
    run = Path(run).resolve(strict=True)
    v3 = read_json(run / 'run.json').get('preparation_contract') == 'context-v3'
    if v3:
        from _contracts_v3 import GraphRecords as Records, project as projector, prior_entities
    else:
        Records, projector = GraphRecords, project
    totals, reasons = Counter(), Counter()
    failures, rows = [], []
    for path in sorted((run / "validated_extractions").glob("*.json")):
        saved = read_json(path)
        request = read_json(run / "requests" / path.name)
        from _contracts import source_text
        source = source_text(request["messages"])
        try:
            extra = {}
            if v3:
                history = native_messages(request['messages'])
                restored = []
                for message in history:
                    if message.get('role') == 'assistant':
                        # Saved provider history is raw JSON; native history was
                        # its accepted tuple projection. Reconstruct only that
                        # source-local initial declaration scope.
                        initial = Records.model_validate_json(message['content'])
                        text, _ = projector(initial, source)
                        restored.append({**message, 'content': text})
                    else:
                        restored.append(message)
                extra['previous_entities'] = prior_entities(restored, source)
            canonical, audit = projector(Records.model_validate(saved["records"]), source, **extra)
            if canonical != saved["canonical_tuples"]:
                failures.append({"request_hash": path.stem, "error": "Canonical replay differs from saved extraction"})
            for key in ["raw_entities", "raw_relationships", "entities", "relationships"]:
                totals[key] += audit[key]
            reasons.update(r["reason"] for r in audit["withheld_records"])
            if not audit["all_records_consumed"] or not audit["all_generated_records_accounted"]:
                failures.append({"request_hash": path.stem, "error": "Incomplete record accounting"})
            rows.append({"request_hash": path.stem,
                         **{k: audit[k] for k in ["raw_entities", "raw_relationships", "entities", "relationships"]},
                         "withheld_records": audit["withheld_records"]})
        except Exception as exc:
            failures.append({"request_hash": path.stem, "error": str(exc)})
    tables = load_tables(run)
    entities = as_rows(tables.get("entities", []))
    relationships = as_rows(tables.get("relationships", []))
    names = {r["title"] for r in entities}
    dangling = [r["id"] for r in relationships if r["source"] not in names or r["target"] not in names]
    coverage = read_json(run / "coverage.json") if (run / "coverage.json").exists() else {}
    manifest = read_json(run / "run.json")
    native_replay = replay_native(run, coverage, read_json(run / 'model_calls.json')['completion_calls'], relationships) if coverage.get('processing_complete') else {'status': 'awaiting_completed_processing'}
    return {"run_directory": str(run), "run_status": manifest["status"],
            "scope": "Each saved JSON extraction occurrence, before native merging; counts are not unique scientific facts.",
            "responses_replayed": len(rows), "occurrences": dict(totals),
            "withheld_reason_counts": dict(reasons.most_common()), "replay_failures": failures,
            "all_saved_extractions_replayed": bool(rows) and not failures,
            "native_entities": len(entities), "native_relationships": len(relationships),
            "dangling_relationships": dangling,
            "native_replay": native_replay,
            "processing_complete": coverage.get("processing_complete", False),
            "text_units": coverage.get("text_units"),
            "text_units_with_successful_extraction": coverage.get("text_units_with_successful_extraction"),
            "semantic_entailment_verified": False,
            "limitations": ["Exact quotations can still be misinterpreted; source-backed semantic review is required.",
                            "Rejected candidates may include recoverable true facts, so rejecting records can reduce recall.",
                            "A completed pipeline does not establish that every important relationship was extracted."],
            "responses": rows}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run", type=Path)
    args = p.parse_args()
    result = inspect(args.run)
    target = args.run / "inspection/validated_record_audit.json"
    write_json(target, result)
    print({k: v for k, v in result.items() if k not in {"responses", "limitations", "native_replay"}})
    print('Native replay:', {k:v for k,v in result['native_replay'].items() if k != 'units'})
    print("Saved:", target.resolve())
    native = result['native_replay']
    native_failed = native.get('status') == 'replayed' and (native.get('errors')
        or not native.get('native_relationship_pair_set_exact_match')
        or not native.get('native_relationship_weights_exact_match'))
    raise SystemExit(1 if result["replay_failures"] or result["dangling_relationships"] or native_failed else 0)
