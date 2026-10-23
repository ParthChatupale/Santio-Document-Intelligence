"""Meaningful regression checks against real source data plus adversarial records."""
import json
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
from research_schema_v2 import ResearchPaper,Method,Dataset,Experiment,MethodConfiguration,Metric,Finding,Evidence
from source_index import SourceIndex,metric_name
from quality_v2 import add_table_measurements,normalize_records,assess_graph


class EvidenceRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=SourceIndex(HERE.parents[1]/'outputs/2610.10539v1.json')

    def paper(self):
        method=Method(name='Tetris3D',role='proposed')
        configs=[MethodConfiguration(name=name,experiment_name='Ablation',method=method) for name in ['Full model (Ours)','w/o Interaction Cond.','w/o V2I Attn.','w/ Amodal3R Attn.']]
        return ResearchPaper(title='Regression fixture',methods=[method],introduced_methods=[method],configurations=configs,experiments=[Experiment(name='Ablation',table_labels=['Table 3'])])

    def test_source_cell_assignment_preserves_ablation_values(self):
        paper,report=add_table_measurements(self.paper(),self.source)
        found={(m.row_label,m.column_label):m for m in paper.experiments[0].measurements}
        self.assertEqual(found['Full model (Ours)','PD'].reported_value,'0.0192')
        self.assertEqual(found['w/o Interaction Cond.','PD'].reported_value,'0.4980')
        self.assertEqual(found['Full model (Ours)','PD'].cell_evidence.cell_ref,'#/tables/2::cell:30')
        self.assertEqual(len(found),56)

    def test_merged_table_is_not_split_or_assigned(self):
        paper=self.paper();paper.experiments=[Experiment(name='Real scenes',table_labels=['Table 2'])]
        paper,report=add_table_measurements(paper,self.source)
        self.assertFalse(paper.experiments[0].measurements)
        self.assertTrue(any(x.get('reason')=='ambiguous_table_cells' for x in report['unresolved']))

    def test_nested_configuration_records_are_not_lost(self):
        paper=self.paper();paper.experiments[0].configurations=paper.configurations;paper.configurations=[]
        paper,_=normalize_records(paper)
        self.assertEqual(len(paper.configurations),4)
        paper,_=add_table_measurements(paper,self.source)
        self.assertEqual(len(paper.experiments[0].measurements),56)

    def test_dense_identity_only_configuration_reference(self):
        paper=self.paper()
        raw=paper.model_dump()
        raw['experiments'][0]['configurations']=[{'name':c.name,'experiment_name':c.experiment_name} for c in paper.configurations]
        fixed,_=normalize_records(ResearchPaper.model_validate(raw))
        self.assertTrue(all(c.method is not None for c in fixed.configurations))
        fixed,_=add_table_measurements(fixed,self.source)
        self.assertEqual(len(fixed.experiments[0].measurements),56)
        from docling_graph.core.converters.graph_converter import GraphConverter
        graph,_=GraphConverter().pydantic_list_to_graph([fixed])
        self.assertEqual(sum(d['label']=='CONFIGURATION_OF' for _,_,d in graph.edges(data=True)),4)

    def test_root_only_extraction_fails_success_gate(self):
        from run_v2 import extraction_is_substantive
        self.assertFalse(extraction_is_substantive({'nodes':[{'label':'ResearchPaper'}],'edges':[]}))
        self.assertTrue(extraction_is_substantive({'nodes':[{'label':'ResearchPaper'},{'label':'Method'}],'edges':[{}]}))

    def test_dense_fallback_cannot_be_reported_as_dense_success(self):
        from run_v2 import contract_outcome
        events=[{'event_type':'extraction_completed','payload':{'source_type':'chunk_batch','parsed_model':None}},
                {'event_type':'extraction_completed','payload':{'source_type':'chunk','parsed_model':{'title':'P'}}}]
        self.assertEqual(contract_outcome(events,'dense'),'direct_fallback_after_dense_failure')

    def test_answer_citations_and_explicit_abstention(self):
        from retrieval_v2 import check_answer
        sources=[{'citation':'S1'}]
        self.assertEqual(check_answer('INSUFFICIENT_EVIDENCE',sources)['answer_status'],'insufficient_evidence')
        self.assertEqual(check_answer('A fabricated answer [S9]',sources)['answer_status'],'citation_check_failed')
        self.assertEqual(check_answer('An uncited answer',sources)['answer_status'],'citation_check_failed')
        self.assertIn('resolvable_citations',check_answer('Reported value 0.0192 [S1]',sources)['answer_status'])

    def test_ambiguous_experiment_mapping_withholds_values(self):
        paper=self.paper();paper.experiments.append(Experiment(name='Other evaluation',table_labels=['Table 3']))
        paper,report=add_table_measurements(paper,self.source)
        self.assertFalse(paper.experiments[0].measurements)

    def test_no_table_experiment_mapping_is_invented(self):
        paper=self.paper();paper.experiments[0].table_labels=[]
        paper,_=add_table_measurements(paper,self.source)
        self.assertFalse(paper.experiments[0].measurements)

    def test_exact_quote_resolves_and_paraphrase_does_not(self):
        quote=self.source.units['#/texts/315'].text
        self.assertEqual(self.source.locate(quote)[0]['ref'],'#/texts/315')
        self.assertFalse(self.source.locate('The authors definitely guarantee that every scene is physically perfect.'))

    def test_wrong_reference_cannot_override_quote(self):
        quote=self.source.units['#/texts/315'].text
        self.assertFalse(self.source.locate(quote,'#/texts/20'))

    def test_metric_concept_duplicate_is_rejected(self):
        g={'nodes':[{'id':'m','label':'Method','name':'Tetris3D'}, {'id':'c','label':'Concept','name':'PD'}, {'id':'v','label':'Metric','name':'PD'}],
           'edges':[{'source':'m','target':'c','label':'USES_CONCEPT'}]}
        assessed,usable,_,_=assess_graph(g,self.source)
        self.assertEqual(assessed['edges'][0]['support_status'],'rejected')
        self.assertFalse(usable['edges'])

    def test_dataset_misclassified_as_method_is_rejected(self):
        g={'nodes':[{'id':'m','label':'Method','name':'ComOb'}, {'id':'d','label':'Dataset','name':'ComOb'}, {'id':'p','label':'ResearchPaper','title':'Paper'}],
           'edges':[{'source':'p','target':'m','label':'DISCUSSES_METHOD'}]}
        self.assertEqual(assess_graph(g,self.source)[0]['nodes'][0]['support_status'],'rejected')

    def test_experiment_title_is_not_a_method(self):
        g={'nodes':[{'id':'x','label':'Method','name':'Quantitative comparison on a benchmark'}],'edges':[]}
        self.assertEqual(assess_graph(g,self.source)[0]['nodes'][0]['support_status'],'rejected')

    def test_unknown_measurement_is_rejected(self):
        g={'nodes':[{'id':'x','label':'Measurement','reported_value':'0.9620','cell_evidence':{'cell_ref':'#/tables/2::cell:30'}}],'edges':[]}
        self.assertEqual(assess_graph(g,self.source)[0]['nodes'][0]['support_status'],'rejected')

    def test_configuration_context_prevents_alias_collapse(self):
        from docling_graph.core.converters.node_id_registry import NodeIDRegistry
        registry=NodeIDRegistry();method=Method(name='Tetris3D')
        a=MethodConfiguration(name='Ours',experiment_name='Main evaluation',method=method)
        b=MethodConfiguration(name='Ours',experiment_name='Shorter training ablation',method=method)
        self.assertNotEqual(registry.get_node_id(a),registry.get_node_id(b))

    def test_converter_reuses_shared_method_and_dataset(self):
        from docling_graph.core.converters.graph_converter import GraphConverter
        a=Method(name='A',built_on=[Method(name='B')],training_datasets=[Dataset(name='D')])
        p=ResearchPaper(title='Fixture',methods=[a,Method(name='B')],datasets=[Dataset(name='D')])
        graph,_=GraphConverter().pydantic_list_to_graph([p])
        self.assertEqual(sum(d['label']=='Method' for _,d in graph.nodes(data=True)),2)
        self.assertEqual(sum(d['label']=='Dataset' for _,d in graph.nodes(data=True)),1)
        self.assertIn('BUILT_ON',[d['label'] for _,_,d in graph.edges(data=True)])

    def test_metric_normalization_keeps_metric_identity(self):
        self.assertEqual(metric_name('Reconstruction Quality - CD-S ↓'),'CD-S')
        paper=ResearchPaper(title='Fixture',metrics=[Metric(name='Reconstruction Quality - CD-S ↓')])
        fixed,log=normalize_records(paper)
        self.assertEqual(fixed.metrics[0].name,'CD-S');self.assertEqual(paper.metrics[0].name,'Reconstruction Quality - CD-S ↓')
        self.assertTrue(log)

    def test_hierarchy_is_derived_by_native_chunker(self):
        chunks=self.source.chunks()
        self.assertTrue(any(c['headings']==['3 METHOD','3.1 OVERVIEW'] for c in chunks))
        self.assertTrue(all(r in self.source.units for c in chunks for r in c['refs']))

    def test_empty_formula_inventory_is_honest(self):
        quality=self.source.inventory([])
        self.assertEqual(quality['empty_formulas'],14)
        self.assertIn('not performed',quality['figure_interpretation'])


if __name__=='__main__':unittest.main()
