import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import write_json
from seed_run_cache import seed


class ExactCacheSeed(TestCase):
    def fixture(self, root):
        source, target = root / 'source', root / 'target'
        manifest = {'status': 'staged', 'input_sha256': 'input', 'settings_sha256': 'settings',
                    'extraction_prompt_sha256': 'prompt', 'scientific_contract_v3_sha256': 'contract'}
        for path in [source, target]:
            write_json(path / 'run.json', manifest)
        request = {'model': 'example', 'messages': [{'role': 'user', 'content': 'Exact request'}]}
        key = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        write_json(source / 'requests' / (key + '.json'), request)
        write_json(source / 'response_cache' / (key + '.json'), {'content': 'raw response'})
        write_json(source / 'validated_extractions' / (key + '.json'), {'canonical_tuples': 'old projection'})
        write_json(source / 'cache/native.json', {'content': 'old native cache'})
        write_json(source / 'model_calls.json', {'completion_calls': []})
        return source, target, key

    def test_revalidation_copies_raw_responses_not_stale_native_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target, key = self.fixture(Path(folder))
            self.assertEqual(seed(source, target, revalidate=True), 1)
            self.assertEqual((source / 'response_cache' / (key + '.json')).read_bytes(),
                             (target / 'response_cache' / (key + '.json')).read_bytes())
            self.assertFalse((target / 'validated_extractions').exists())
            self.assertFalse((target / 'cache').exists())
            self.assertFalse((target / 'output').exists())

    def test_fabricated_request_cache_alias_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target, key = self.fixture(Path(folder))
            write_json(source / 'requests' / (key + '.json'), {'model': 'different-request'})
            with self.assertRaisesRegex(ValueError, 'fingerprint mismatch'):
                seed(source, target, revalidate=True)

    def test_changed_prompt_cannot_be_seeded_as_equivalent(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target, _ = self.fixture(Path(folder))
            write_json(target / 'run.json', {'status': 'staged', 'input_sha256': 'input',
                'settings_sha256': 'settings', 'extraction_prompt_sha256': 'changed',
                'scientific_contract_v3_sha256': 'contract'})
            with self.assertRaisesRegex(ValueError, 'Incompatible'):
                seed(source, target, revalidate=True)

    def test_pacing_concurrency_can_change_without_aliasing_prompt_or_chunking(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target, _ = self.fixture(Path(folder))
            write_json(source / 'settings.yaml', {'concurrent_requests': 1, 'chunking': {'size': 1024}})
            write_json(target / 'settings.yaml', {'concurrent_requests': 2, 'chunking': {'size': 1024}})
            manifest = json.loads((target / 'run.json').read_text())
            manifest['settings_sha256'] = 'pacing-changed'
            write_json(target / 'run.json', manifest)
            self.assertEqual(seed(source, target, revalidate=True), 1)
            write_json(target / 'settings.yaml', {'concurrent_requests': 2, 'chunking': {'size': 512}})
            with self.assertRaisesRegex(ValueError, 'Incompatible'):
                seed(source, target, revalidate=True)
