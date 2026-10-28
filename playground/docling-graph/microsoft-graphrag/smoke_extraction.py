"""Run native two-pass extraction on selected prepared records before indexing.

Uses the staged run's real prompt and private provider. Raw requests/responses
remain in that run; only identical requests can later hit its provider cache.
No graph output table or reference answer is injected into extraction.
"""
import argparse
import asyncio
from pathlib import Path
from types import SimpleNamespace

from _common import read_json, write_json
from _providers import Runtime, unresolved_failures


async def smoke(run, refs, ids, model=None):
    from graphrag.index.operations.extract_graph.graph_extractor import GraphExtractor
    import yaml
    records = read_json(run / 'input/documents.json')
    selected = [r for r in records if r['id'] in ids or set(refs).intersection(r['docling_refs'])]
    if not selected:
        raise ValueError('No selected records')
    settings = yaml.safe_load((run / 'settings.yaml').read_text(encoding='utf-8'))
    prompt = (run / 'prompts/extract_graph.txt').read_text(encoding='utf-8')
    runtime = Runtime(run, max_calls=45, max_tokens=700000, max_seconds=900)
    if model:
        runtime.model = model
        runtime.fallback_model = model
    async def complete(**kwargs):
        return await asyncio.to_thread(runtime.complete, **kwargs)
    model = SimpleNamespace(completion_async=complete)
    sem = asyncio.Semaphore(settings.get('concurrent_requests', 1))
    async def one(record):
        async with sem:
            errors = []
            extractor = GraphExtractor(model, prompt, 1, on_error=lambda error, *_: errors.append(str(error)))
            entities, relationships = await extractor(record['text'].strip(),
                settings['extract_graph']['entity_types'], record['id'])
            result = {'record_id': record['id'], 'docling_refs': record['docling_refs'],
                      'entities': entities.to_dict('records'), 'relationships': relationships.to_dict('records'),
                      'errors': errors}
            print(record['id'], len(entities), 'entities', len(relationships), 'relationships', errors, flush=True)
            return result
    try:
        results = await asyncio.gather(*(one(r) for r in selected))
    finally:
        runtime.close()
    report = {'records': results, 'unresolved_calls': unresolved_failures(runtime.calls),
              'note': 'Native extraction smoke test, not independent semantic validation.'}
    write_json(run / 'verification/extraction_smoke.json', report)
    return 1 if report['unresolved_calls'] or any(r['errors'] for r in results) else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--item-ref', action='append', default=[])
    parser.add_argument('--record-id', action='append', default=[])
    parser.add_argument('--model', help='Explicit per-trial model override; the actual model is saved in every request')
    args = parser.parse_args()
    raise SystemExit(asyncio.run(smoke(args.run.resolve(strict=True), args.item_ref, args.record_id, args.model)))
