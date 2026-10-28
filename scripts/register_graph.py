"""Publish a completed, reviewed graph artifact into Santio's optional graph feature.

Copies data, not playground code or question history. Does not index or call APIs.
"""
import argparse
import json
from pathlib import Path
import shutil

from pbl_docintel.gui.server import Workspace, fingerprint
from pbl_docintel.gui.imports import atomic_json


def register(root, source, paper_id, python):
    root, source = Path(root).resolve(strict=True), Path(source).resolve(strict=True)
    python = Path(python).resolve(strict=True)
    workspace = Workspace(root)
    paper = workspace.papers[paper_id]
    pdf = workspace.path(paper['source_pdf'])
    manifest = json.loads((source / 'run.json').read_text(encoding='utf-8'))
    coverage = json.loads((source / 'coverage.json').read_text(encoding='utf-8'))
    audit = json.loads((source / 'inspection/validated_record_audit.json').read_text(encoding='utf-8'))
    if (manifest['status'] != 'completed' or not coverage.get('processing_complete')
            or not audit.get('all_saved_extractions_replayed')
            or not audit.get('native_replay', {}).get('native_relationship_pair_set_exact_match')):
        raise ValueError('Publish only a completed graph that passed native replay.')
    if fingerprint(Path(manifest['source'])) != manifest['source_sha256']:
        raise ValueError('The graph source extraction has changed.')
    if not (source / 'evaluations/source-review/semantic_review.json').exists():
        raise ValueError('Publish the source-review findings with the graph.')
    # The PDF must be the one used by the reviewed source extraction, not merely
    # another paper assigned the same graph in the UI.
    expected_pdf = root / (Path(manifest['source']).stem + '.pdf')
    if not expected_pdf.is_file() or fingerprint(expected_pdf) != fingerprint(pdf):
        raise ValueError('The selected paper does not match the reviewed graph PDF.')
    import hashlib
    target = root / 'data/graph-rag/artifacts' / hashlib.sha256(paper_id.encode()).hexdigest()[:20] / source.name
    if not target.resolve().is_relative_to((root / 'data/graph-rag/artifacts').resolve()):
        raise ValueError('Artifact path escaped graph storage.')
    if target.exists():
        raise ValueError('This artifact is already published; use a new version for replacement.')
    target.mkdir(parents=True)
    required = ['run.json', 'settings.yaml', 'source_map.json', 'coverage.json',
                'model_calls.json', 'input/documents.json', 'prompts/extract_graph.txt',
                'inspection/validated_record_audit.json',
                'evaluations/source-review/semantic_review.json']
    for name in required:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, destination)
    for directory in ['output', 'vectors', 'validated_extractions']:
        shutil.copytree(source / directory, target / directory)
    for sidecar in (target / 'validated_extractions').glob('*.json'):
        (target / 'requests').mkdir(exist_ok=True)
        shutil.copy2(source / 'requests' / sidecar.name, target / 'requests' / sidecar.name)
    receipt = {'source_run': str(source), 'paper_id': paper_id,
               'pdf_sha256': fingerprint(pdf), 'docling_sha256': manifest['source_sha256'],
               'files': {str(p.relative_to(target)).replace('\\', '/'): fingerprint(p)
                         for p in target.rglob('*') if p.is_file()}}
    atomic_json(target / 'import_receipt.json', receipt)
    registry_path = root / 'data/graph-rag/registry.json'
    registry = json.loads(registry_path.read_text(encoding='utf-8')) if registry_path.exists() else {'papers': {}}
    registry['python'] = str(python)
    registry['papers'][paper_id] = {'run': str(target.relative_to(root)).replace('\\', '/'),
        'run_name': source.name, 'pdf_sha256': receipt['pdf_sha256'],
        'docling_sha256': manifest['source_sha256']}
    atomic_json(registry_path, registry)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--paper-id', required=True)
    parser.add_argument('--graph-python', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(register(args.workspace, args.run, args.paper_id, args.graph_python))
