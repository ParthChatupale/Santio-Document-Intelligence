"""Section batching, budget and real native merge/converter regressions."""
from pathlib import Path
import hashlib
import json
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
from run_sections import make_batches,merge_sections
from research_schema_v2 import ResearchPaper,Method,Concept,Evidence


class SectionTests(unittest.TestCase):
    def chunk(self,name,heading,text):
        return {'id':name,'refs':[name],'headings':[heading],'pages':[1],'text':text}

    def test_batches_preserve_all_selected_content_and_heading_boundaries(self):
        chunks=[self.chunk('a','A','x'*120),self.chunk('b','A','y'*120),self.chunk('c','B','z'*120),self.chunk('r','References','Reference')]
        selected,batches=make_batches(chunks,[],len,260)
        self.assertEqual([c['id'] for c in selected],['a','b','c'])
        self.assertEqual([c['id'] for b in batches for c in b['chunks']],['a','b','c'])
        self.assertTrue(all(len({c['headings'][0] for c in b['chunks']})==1 for b in batches))
        self.assertTrue(all(b['estimated_body_tokens']<=260 for b in batches))

    def test_oversize_chunk_is_marked_without_truncation(self):
        chunk=self.chunk('a','A','x'*1000)
        _,batches=make_batches([chunk],['A'],len,100)
        self.assertTrue(batches[0]['oversize'])
        self.assertEqual(batches[0]['chunks'][0]['text'],chunk['text'])

    def test_heading_selection_is_exact_and_case_insensitive(self):
        chunks=[self.chunk('a','Training','Some text'),self.chunk('b','Training data','Other text')]
        selected,_=make_batches(chunks,['training'],len,1000)
        self.assertEqual([c['id'] for c in selected],['a'])

    def test_native_merge_preserves_shared_entity_evidence_and_relations(self):
        a=ResearchPaper(title='Fixture',methods=[Method(name='A',built_on=[Method(name='B')],evidence=[Evidence(quote='A builds on B.',source_ref='one')])])
        b=ResearchPaper(title='Fixture',methods=[Method(name='A',concepts=[Concept(name='C')],evidence=[Evidence(quote='A uses C.',source_ref='two')])])
        merged=merge_sections([a,b])
        self.assertEqual(len(merged.methods),1)
        self.assertEqual({e.source_ref for e in merged.methods[0].evidence},{'one','two'})
        from docling_graph.core.converters.graph_converter import GraphConverter
        graph,_=GraphConverter(alias_llm_fn=None).pydantic_list_to_graph([merged])
        labels={d['label'] for _,_,d in graph.edges(data=True)}
        self.assertTrue({'BUILT_ON','USES_CONCEPT'}<=labels)

    def test_request_budget_prevents_api_call(self):
        from docling_graph.llm_clients.config import resolve_effective_model_config
        from nvidia_client import NvidiaClient
        client=NvidiaClient(resolve_effective_model_config('openai','openai/nvidia/nemotron-3-super-120b-a12b'),max_calls=0)
        with patch('docling_graph.llm_clients.litellm.LiteLLMClient._call_api') as call:
            with self.assertRaisesRegex(RuntimeError,'budget'):
                client._call_api([])
            call.assert_not_called()
        self.assertTrue(client.budget_exhausted)

    def test_recovery_cannot_overlap_running_extraction(self):
        from retry_section_batch import retry
        with TemporaryDirectory() as directory:
            folder=Path(directory)
            (folder/'run.json').write_text(json.dumps({'status':'running'}),encoding='utf-8')
            with patch('retry_section_batch.load_connection') as connection:
                with self.assertRaisesRegex(ValueError,'current extraction process'):
                    retry(folder,1)
                connection.assert_not_called()

    def test_recovery_preserves_original_call_budget(self):
        from retry_section_batch import retry
        with TemporaryDirectory() as directory:
            folder=Path(directory);source=folder/'source.json';source.write_bytes(b'{}')
            manifest={'status':'partial_document_extraction','input':{'source':str(source),'source_sha256':hashlib.sha256(b'{}').hexdigest()},'configuration':{'max_calls':1}}
            (folder/'run.json').write_text(json.dumps(manifest),encoding='utf-8')
            (folder/'model_calls.json').write_text(json.dumps([{'request':1,'status':'complete'}]),encoding='utf-8')
            with patch('retry_section_batch.load_connection') as connection:
                with self.assertRaisesRegex(ValueError,'budget is exhausted'):
                    retry(folder,1)
                connection.assert_not_called()


if __name__=='__main__':unittest.main()
