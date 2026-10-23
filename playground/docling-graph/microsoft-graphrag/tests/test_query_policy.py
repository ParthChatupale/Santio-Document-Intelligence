import sys
from pathlib import Path
from types import SimpleNamespace
import tempfile
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _query_policy import apply_profile
from graphrag.config.models.local_search_config import LocalSearchConfig
from graphrag.config.models.basic_search_config import BasicSearchConfig


class QueryPolicy(TestCase):
    def test_native_baseline_unchanged_and_tuned_prompt_is_inspectable(self):
        cfg = SimpleNamespace(local_search=LocalSearchConfig(max_context_tokens=6000,
            top_k_entities=8, top_k_relationships=12), basic_search=BasicSearchConfig())
        before = cfg.local_search.model_dump()
        with tempfile.TemporaryDirectory() as folder:
            apply_profile(cfg, 'local', folder, 'native')
            self.assertEqual(cfg.local_search.model_dump(), before)
            result = apply_profile(cfg, 'local', folder, 'source-focused')
            prompt = Path(cfg.local_search.prompt).read_text()
            self.assertIn('{context_data}', prompt)
            self.assertIn('original Sources passages', prompt)
            self.assertNotIn('incorporating any relevant general knowledge', prompt)
            self.assertNotIn('Tetris3D', prompt)
            self.assertGreater(cfg.local_search.max_context_tokens, before['max_context_tokens'])
            self.assertTrue(result['query_prompt_sha256'])

    def test_unsupported_profile_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            apply_profile(None, 'global', '.', 'source-focused')
