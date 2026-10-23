"""Bounded relationship-only pass over a saved section trial; no PDF conversion."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

from sandbox import HERE, load_connection, write_json


def run(args):
    import tiktoken
    from docling_graph.core.extractors.backends.llm_backend import LlmBackend
    from docling_graph.llm_clients.config import resolve_effective_model_config
    from nvidia_client import NvidiaClient
    from relationship_pass import RelationshipBatch, FocusedRelationshipBatch, RULES, FOCUSED_RULES, validate_batch, project_relationships, relationship_gate
    from research_schema_v2 import ResearchPaper
    from run_sections import make_batches
    from run_v2 import postprocess
    from source_index import SourceIndex

    origin = args.run.resolve()
    previous = json.loads((origin / 'run.json').read_text(encoding='utf-8'))
    if previous['status'] == 'running':
        raise ValueError('Wait for the original extraction to finish')
    source = SourceIndex(previous['input']['source'])
    if source.document_id != previous['input']['source_sha256']:
        raise ValueError('The source has changed since extraction')
    selected = json.loads((origin / 'selected_chunks.json').read_text(encoding='utf-8'))
    enc = tiktoken.get_encoding('cl100k_base')
    count = lambda s: len(enc.encode(s, disallowed_special=()))
    selected, batches = make_batches(selected, args.heading, count, args.batch_tokens)
    if not batches:
        raise ValueError('No matching source chunks')
    original_record=json.loads((origin / 'extracted_records.json').read_text(encoding='utf-8'))[0]
    title=original_record['title']
    entity_types={}
    from source_index import normalized
    for catalog,kind in [('methods','Method'),('datasets','Dataset'),('concepts','Concept')]:
        for item in original_record[catalog]:
            entity_types.setdefault(normalized(item['name']),set()).add(kind)
    template=FocusedRelationshipBatch
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = HERE / 'outputs' / f"{Path(source.path).stem}-relationships-{stamp}"
    (folder / 'batches').mkdir(parents=True)
    model, base, secret = load_connection()
    overrides = {'connection': {'base_url': base}, 'generation': {'temperature': 0.0, 'max_tokens': args.max_output_tokens},
                 'reliability': {'timeout_s': args.timeout, 'max_retries': 0},
                 'context_limit': 131072, 'max_output_tokens': args.max_output_tokens}

    class ScopedClient(NvidiaClient):
        batch_dir = None
        def get_json_response(self, prompt, **kwargs):
            scoped = {**prompt, 'system': prompt['system'] + RULES + FOCUSED_RULES}
            estimated = count(scoped['system']) + count(scoped['user']) + 12
            if estimated > args.estimated_input_cap:
                raise ValueError('Estimated input exceeds configured ceiling')
            write_json(self.batch_dir / 'prompt.json', scoped)
            try:
                return super().get_json_response(scoped, **kwargs)
            finally:
                write_json(self.batch_dir / 'response.json', {'raw': self.last_call_diagnostics.get('raw_response')})

    client = ScopedClient(resolve_effective_model_config('openai', f'openai/{model}', overrides=overrides),
                          thinking=False, sdk_retries=0, max_calls=args.max_calls)
    backend = LlmBackend(client, extraction_contract='direct', structured_output=False,
                         dense_config={'gleaning_enabled': False, 'retry_on_truncation': False, 'llm_input_format': 'markdown'})
    manifest = {**previous, 'status': 'running', 'origin_run': str(origin), 'started_at': datetime.now(timezone.utc).isoformat(),
                'actual_contract': 'bounded_native_relationship_projection', 'batches': [],
                'configuration': {'model': model, 'base_url': base, 'temperature': 0, 'max_calls': args.max_calls,
                    'max_output_tokens': args.max_output_tokens, 'batch_tokens': args.batch_tokens, 'timeout': args.timeout,
                    'max_seconds': args.max_seconds, 'thinking': False, 'sdk_retries': 0, 'provider_retries': 0},
                'analysis_scope': {**previous['analysis_scope'], 'relationship_review_chunks': len(selected),
                                   'relationship_review_refs': sorted({r for c in selected for r in c['refs']})},
                'latest_pointer_updated': False}
    # Freeze the existing development reference before sending any requests.
    reference = json.loads(args.reference.read_text(encoding='utf-8'))
    if reference['source_sha256'] != source.document_id:
        raise ValueError('Reference source hash mismatch')
    write_json(folder / 'development_reference.json', reference)
    manifest['configuration']['relationship_contract']='required_typed_groups_v2'
    manifest['configuration']['relationship_schema_sha256']=hashlib.sha256(json.dumps(template.model_json_schema(),sort_keys=True).encode()).hexdigest()
    write_json(folder / 'relationship_schema.json', template.model_json_schema())
    write_json(folder / 'schema.json', ResearchPaper.model_json_schema())
    write_json(folder / 'selected_chunks.json', json.loads((origin / 'selected_chunks.json').read_text(encoding='utf-8')))
    write_json(folder / 'run.json', manifest)
    rows = []; started = perf_counter()
    print(f'Run: {folder}\nRelationship pass: {len(selected)} chunks in {len(batches)} batches; maximum {args.max_calls} calls.', flush=True)
    try:
        for i, batch in enumerate(batches, 1):
            allowed = {r for c in batch['chunks'] for r in c['refs']}
            row = {'batch': i, 'heading': batch['heading'], 'refs': sorted(allowed), 'status': 'pending'}
            manifest['batches'].append(row)
            if batch.get('oversize'):
                row['status'] = 'skipped_oversize'; continue
            if len(client.calls) >= args.max_calls or perf_counter() - started + args.timeout > args.max_seconds:
                row['status'] = 'not_attempted_budget'; continue
            client.batch_dir = folder / 'batches' / f'{i:03d}'; client.batch_dir.mkdir()
            # Resolve full supplied items locally. Do not send unrelated document sections.
            body = f'Paper: {title}\nSection: {batch["heading"]}\nNamed Dataset catalog: '+json.dumps([d['name'] for d in original_record['datasets']])+ '\n\n' + '\n\n'.join(
                f'[Source reference: {ref}]\n{source.units[ref].text}' for ref in sorted(allowed))
            before = len(client.calls)
            print(f'Relationship batch {i}/{len(batches)}: {batch["heading"]}', flush=True)
            record = backend.extract_from_markdown(body, template, context=f'relationship batch {i}', is_partial=True, allow_dense=False)
            calls = client.calls[before:]
            row['call_numbers'] = [c['request'] for c in calls]
            if any(c.get('finish_reason') == 'length' for c in calls):
                row['status'] = 'truncated'
            elif record is None:
                row['status'] = 'failed'
            else:
                canonical=record.as_relationship_batch()
                validated, issues = validate_batch(canonical, source, allowed,entity_types)
                rows.extend(validated)
                write_json(client.batch_dir / 'validated.json', record.model_dump(mode='json'))
                write_json(client.batch_dir / 'validation.json', {'relationships': validated, 'issues': issues})
                row.update(status='reviewed_with_issues' if issues or any(not r['accepted'] for r in validated) else 'reviewed',
                           accepted=sum(r['accepted'] for r in validated), rejected=sum(not r['accepted'] for r in validated), issues=issues)
            write_json(folder / 'run.json', manifest); write_json(folder / 'model_calls.json', client.calls)
            print(f'Batch {i}: {row["status"]}; accepted {row.get("accepted", 0)}, withheld {row.get("rejected", 0)}', flush=True)

        base_paper = ResearchPaper.model_validate(json.loads((origin / 'extracted_records.json').read_text(encoding='utf-8'))[0])
        paper = project_relationships(base_paper, rows)
        write_json(folder / 'relationship_candidates.json', rows)
        write_json(folder / 'extracted_records.json', [paper.model_dump(mode='json')])
        write_json(folder / 'model_calls.json', client.calls)
        manifest['elapsed_seconds'] = round(perf_counter() - started, 2)
        manifest['batch_statuses']=dict(Counter(b['status'] for b in manifest['batches']))
        manifest['relationship_extraction_status'] = 'candidates_require_semantic_review'
        write_json(folder / 'run.json', manifest)
        final = postprocess(folder)
        from evaluate_sections import evaluate
        evaluation = evaluate(folder, args.reference)
        graph = json.loads((folder / 'usable_graph.json').read_text(encoding='utf-8'))
        gate = relationship_gate(graph)
        # Check the frozen expected dependencies AND their expected source refs.
        lookup = {n['id']: n for n in graph['nodes']}
        checks = []
        from source_index import normalized
        for item in reference['checks']:
            if item['kind'] != 'edge': continue
            matches = [e for e in graph['edges'] if e['label'] == item['relation'] and
                       normalized(lookup[e['source']].get('name', '')) == normalized(item['source']) and
                       normalized(lookup[e['target']].get('name', '')) == normalized(item['target']) and
                       set(e.get('source_refs', [])) & set(item['refs'])]
            checks.append({**item, 'passed': bool(matches)})
        reference_passed = bool(checks) and all(c['passed'] for c in checks) and not any(f['present'] for f in evaluation['forbidden'])
        gate.update(development_reference_passed=reference_passed, expected_relationship_checks=checks)
        gate['passed'] = gate['passed'] and reference_passed
        review_complete = all(b['status'] == 'reviewed' for b in manifest['batches']) and len(manifest['batches']) == len(batches)
        report = {'accepted_proposals': sum(r['accepted'] for r in rows), 'withheld_proposals': sum(not r['accepted'] for r in rows),
                  'review_complete_for_selected_scope': review_complete, 'relationship_gate': gate,
                  'note': 'Development checks and exact source linkage, not independent semantic accuracy or exhaustive recall.'}
        write_json(folder / 'relationship_report.json', report)
        final.update(status='partial_document_extraction', relationship_gate=gate,
                     relationship_extraction_status='source_linked_candidates_development_checks_passed' if gate['passed'] else 'relationship_checks_failed',
                     elapsed_seconds=round(perf_counter() - started, 2), batch_statuses=dict(Counter(b['status'] for b in manifest['batches'])),
                     token_usage={'input': sum(c.get('usage', {}).get('prompt_tokens', 0) for c in client.calls),
                                  'output': sum(c.get('usage', {}).get('completion_tokens', 0) for c in client.calls),
                                  'incomplete_due_to_failed_requests': any(c['status'] == 'failed' for c in client.calls)})
        final['extraction_gate']['passed'] = final['extraction_gate']['passed'] and gate['passed'] and review_complete
        if not final['extraction_gate']['passed']:
            final['extraction_gate']['reason']='Relationship development checks or source reviews remain unresolved; preserve as a partial trial.'
        write_json(folder / 'run.json', final)
        quality = json.loads((folder / 'quality_report.json').read_text(encoding='utf-8'))
        original_quality = json.loads((origin / 'quality_report.json').read_text(encoding='utf-8'))
        quality['sections'] = original_quality['sections']
        quality['analysis_scope'] = manifest['analysis_scope']; quality['relationship_review'] = report
        write_json(folder / 'quality_report.json', quality)
        write_json(HERE / 'outputs/latest_relationship_trial.json', {'run_dir': str(folder), 'status': final['status'], 'relationship_gate': gate})
        print(json.dumps({'run': str(folder), 'nodes': final['nodes'], 'edges': final['edges'], **report}, indent=2), flush=True)
        return 0 if final['extraction_gate']['passed'] else 2
    except (Exception, KeyboardInterrupt) as error:
        manifest.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed', error_type=type(error).__name__)
        write_json(folder / 'run.json', manifest); write_json(folder / 'model_calls.json', client.calls)
        write_json(folder / 'relationship_candidates.json', rows)
        print(str(error).replace(secret, '[REDACTED]')[:800], file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8'); sys.stderr.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True, type=Path)
    p.add_argument('--heading', action='append', default=[])
    p.add_argument('--reference', type=Path, default=HERE / 'evaluation/survey_sections_reference.json')
    for name, value in [('batch-tokens', 900), ('max-output-tokens', 4096), ('estimated-input-cap', 10000),
                        ('max-calls', 10), ('timeout', 90), ('max-seconds', 900)]:
        p.add_argument('--' + name, type=int, default=value)
    args = p.parse_args()
    if min(args.batch_tokens, args.max_output_tokens, args.estimated_input_cap, args.max_calls, args.timeout, args.max_seconds) <= 0:
        p.error('Budgets must be positive')
    raise SystemExit(run(args))
