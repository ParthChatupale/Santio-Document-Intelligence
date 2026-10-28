"""Seed only exact saved API requests and native completion caches for a new run.

Input, settings, extraction prompt and scientific-contract hashes must match.
Never copies output tables, vectors, model usage ledgers or fabricated cache keys.
The original attempt ledgers remain the authority for historical API usage.
"""
import argparse
from pathlib import Path
import shutil

from _common import read_json, write_json, digest


def seed(source, target, revalidate=False):
    source, target = Path(source).resolve(strict=True), Path(target).resolve(strict=True)
    before, after = read_json(source / 'run.json'), read_json(target / 'run.json')
    if after['status'] != 'staged':
        raise ValueError('Seed only a new staged run')
    for key in ['input_sha256', 'settings_sha256', 'extraction_prompt_sha256', 'scientific_contract_v3_sha256']:
        if revalidate and key in {'input_sha256', 'scientific_contract_v3_sha256'}:
            continue
        if revalidate and key == 'settings_sha256' and before.get(key) != after.get(key):
            import yaml
            configs = [yaml.safe_load((p / 'settings.yaml').read_text(encoding='utf-8')) for p in [source, target]]
            for config in configs:
                config.pop('concurrent_requests', None)
            if configs[0] == configs[1]:
                continue
        if not before.get(key) or before.get(key) != after.get(key):
            raise ValueError('Incompatible cached extraction: ' + key)
    copied = []
    for path in (source / 'response_cache').glob('*.json'):
        request_path = source / 'requests' / path.name
        if not request_path.exists():
            raise ValueError('Cached response lacks original request')
        # Request filenames are actual fingerprints, not aliases for new prompts.
        import hashlib, json
        request = read_json(request_path)
        actual_key = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        if actual_key != path.stem:
            raise ValueError('Request fingerprint mismatch')
        for name in ['response_cache', 'requests', 'provider_responses'] + ([] if revalidate else ['validated_extractions']):
            original = source / name / path.name
            if original.exists():
                destination = target / name / path.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, destination)
        copied.append(path.stem)
    # Native completion caches can bypass first-pass provider calls. Their
    # identical contract and actual raw sidecars are required above. Failed
    # completion attempts do not produce a successful native cache entry.
    if not revalidate and (source / 'cache').exists():
        shutil.copytree(source / 'cache', target / 'cache', dirs_exist_ok=True)
    write_json(target / 'cache_origin.json', {'source_run': str(source),
        'source_usage_sha256': digest(source / 'model_calls.json'),
        'source_cache_lineage': read_json(source / 'cache_origin.json') if (source / 'cache_origin.json').exists() else None,
        'exact_actual_request_hashes': copied,
        'revalidate_saved_raw_responses': revalidate,
        'note': 'Identical raw API and native completion caches. Native graph outputs and vectors rebuilt. Prior API usage remains in the source ledger.'})
    return len(copied)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    parser.add_argument('--revalidate', action='store_true', help='Import raw API cache only; revalidate every selected response and rebuild all native outputs')
    args = parser.parse_args()
    print('Seeded exact requests:', seed(args.source, args.target, args.revalidate))
