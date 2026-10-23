"""Evidence, omission and direction checks for explicit relationship projection."""
import json
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
from pydantic import ValidationError
from relationship_pass import RelationshipBatch,Relationship,validate_relationship,validate_batch,project_relationships,attach_edge_evidence,relationship_gate
from source_index import SourceIndex
from research_schema_v2 import ResearchPaper,Method


class RelationshipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=SourceIndex(HERE.parents[1]/'outputs/2307.06435v10.json')

    def proposal(self):
        return {'subject':{'name':'WizardCoder','kind':'Method'},'predicate':'BUILT_ON',
                'object':{'name':'StarCoder','kind':'Method'},
                'evidence':[{'source_ref':'#/texts/303','quote':'WizardCoder [164] (fine-tuned StarCoder)'}],
                'explanation':'The passage explicitly identifies the fine-tuned base.'}

    def test_entity_only_response_cannot_validate(self):
        with self.assertRaises(ValidationError):
            RelationshipBatch.model_validate({'methods':[{'name':'WizardCoder'}]})
        with self.assertRaises(ValidationError):
            RelationshipBatch.model_validate({'relationships':[]})

    def test_genuine_empty_review_does_not_pass_graph_gate(self):
        record=RelationshipBatch.model_validate({'relationships':[], 'source_reviews':[
            {'source_ref':'#/texts/303','outcome':'no_supported_relation','reason':'Test omission'}]})
        _,issues=validate_batch(record,self.source,{'#/texts/303'})
        self.assertFalse(issues)  # Review syntax alone is NOT completeness proof.
        self.assertFalse(relationship_gate({'nodes':[{'id':'p','label':'ResearchPaper'},{'id':'m','label':'Method'}],
                                           'edges':[{'source':'p','target':'m','label':'DISCUSSES_METHOD','support_status':'source_linked'}]})['passed'])

    def test_valid_fine_tuning_relation_survives_native_conversion_and_assessment(self):
        from docling_graph.core.converters.graph_converter import GraphConverter
        from quality_v2 import assess_graph,normalize_records
        from run_v2 import graph_json
        row=validate_relationship(self.proposal(),self.source,{'#/texts/303'})
        self.assertTrue(row['accepted'])
        paper=project_relationships(ResearchPaper(title='Fixture',methods=[Method(name='WizardCoder')]),[row])
        paper,_=normalize_records(paper)
        graph,_=GraphConverter(alias_llm_fn=None).pydantic_list_to_graph([paper])
        assessed,usable,_,_=assess_graph(attach_edge_evidence(graph_json(graph),[row]),self.source)
        edges=[e for e in usable['edges'] if e['label']=='BUILT_ON']
        self.assertEqual(len(edges),1)
        self.assertEqual(edges[0]['source_refs'],['#/texts/303'])
        self.assertTrue(edges[0]['relationship_evidence'])
        self.assertTrue(relationship_gate(usable)['passed'])
        self.assertEqual(relationship_gate(usable)['completeness'],'not_established')

    def test_wrong_ref_and_unprovided_ref_are_withheld(self):
        proposal=self.proposal();proposal['evidence'][0]['source_ref']='#/texts/302'
        row=validate_relationship(proposal,self.source,{'#/texts/302'})
        self.assertIn('quote_not_found_at_reference',row['reasons'])
        row=validate_relationship(self.proposal(),self.source,{'#/texts/302'})
        self.assertIn('evidence_outside_supplied_scope',row['reasons'])

    def test_paraphrased_and_unrelated_quotations_are_withheld(self):
        proposal=self.proposal();proposal['evidence'][0]['quote']='WizardCoder definitely builds directly on StarCoder.'
        self.assertFalse(validate_relationship(proposal,self.source,{'#/texts/303'})['accepted'])
        proposal=self.proposal();proposal['object']['name']='LLaMA'
        self.assertIn('endpoint_names_missing_from_quotations',validate_relationship(proposal,self.source,{'#/texts/303'})['reasons'])

    def test_longer_hyphenated_model_name_is_not_base_model_evidence(self):
        from relationship_pass import contains_name
        self.assertFalse(contains_name('LLaMA-GPT-4','LLaMA'))
        self.assertTrue(contains_name('fine-tuned LLaMA on instructions','LLaMA'))
        self.assertTrue(contains_name('trained from LLaMA-GPT-4','LLaMA-GPT-4'))

    def test_reference_requires_expected_relation_source_not_unrelated_cooccurrence(self):
        from relationship_pass import check_development_relationships
        graph={'nodes':[{'id':'a','label':'Method','name':'A'},{'id':'b','label':'Method','name':'B'}],
               'edges':[{'source':'a','target':'b','label':'BUILT_ON','source_refs':['other'],'support_status':'source_linked'}]}
        reference={'checks':[{'kind':'edge','source':'A','target':'B','relation':'BUILT_ON','refs':['expected']}],'forbidden':[]}
        self.assertFalse(check_development_relationships(graph,reference)['passed'])
        graph['edges'][0]['source_refs']=['expected']
        self.assertTrue(check_development_relationships(graph,reference)['passed'])

    def test_wrong_endpoint_type_withheld(self):
        proposal=self.proposal();proposal['object']['kind']='Dataset'
        self.assertIn('invalid_endpoint_types',validate_relationship(proposal,self.source,{'#/texts/303'})['reasons'])

    def test_unknown_generated_data_cannot_become_named_training_dataset(self):
        proposal={'subject':{'name':'Alpaca','kind':'Method'},'predicate':'TRAINED_ON',
                  'object':{'name':'textdavinci-003','kind':'Dataset'},'explanation':'Adversarial model-as-data label',
                  'evidence':[{'source_ref':'#/texts/302','quote':self.source.units['#/texts/302'].text}]}
        result=validate_relationship(proposal,self.source,{'#/texts/302'},{'alpaca':{'Method'},'sharegpt.com':{'Dataset'}})
        self.assertIn('training_dataset_not_in_named_catalog',result['reasons'])

    def test_typed_dependency_maps_to_builtin_relation_with_fixed_types(self):
        from relationship_pass import FocusedRelationshipBatch
        raw={'model_dependencies':[{'derived_model':'WizardCoder','base_model':'StarCoder',
             'evidence':self.proposal()['evidence'],'explanation':'Fine-tuned base'}],
             'training_relations':[],'component_relations':[],'concept_relations':[],
             'source_reviews':[{'source_ref':'#/texts/303','outcome':'relations_found','reason':'Fine-tuned base'}]}
        record=FocusedRelationshipBatch.model_validate(raw).as_relationship_batch()
        self.assertEqual(record.relationships[0].predicate,'BUILT_ON')
        self.assertEqual(record.relationships[0].object.kind,'Method')
        rows,issues=validate_batch(record,self.source,{'#/texts/303'})
        self.assertTrue(rows[0]['accepted']);self.assertFalse(issues)

    def test_catalog_type_conflict_is_not_silently_accepted(self):
        proposal=self.proposal()
        result=validate_relationship(proposal,self.source,{'#/texts/303'},{'starcoder':{'Dataset'}})
        self.assertIn('endpoint_type_conflicts_with_catalog',result['reasons'])

    def test_retrieval_database_is_not_accepted_as_training_corpus(self):
        proposal={'subject':{'name':'RETRO','kind':'Method'},'predicate':'TRAINED_ON',
                  'object':{'name':'MassiveText','kind':'Dataset'},'explanation':'Adversarial fixture',
                  'evidence':[{'source_ref':'#/texts/331','quote':self.source.units['#/texts/331'].text}]}
        self.assertIn('training_vs_retrieval_ambiguous',validate_relationship(proposal,self.source,{'#/texts/331'})['reasons'])

    def test_coverage_cannot_silently_omit_a_source(self):
        record=RelationshipBatch.model_validate({'relationships':[self.proposal()],'source_reviews':[]})
        _,issues=validate_batch(record,self.source,{'#/texts/303'})
        self.assertIn('source_review_coverage_mismatch',issues)

    def test_claim_of_no_relation_cannot_hide_emitted_relation(self):
        record=RelationshipBatch.model_validate({'relationships':[self.proposal()],'source_reviews':[
            {'source_ref':'#/texts/303','outcome':'no_supported_relation','reason':'Contradictory fixture'}]})
        _,issues=validate_batch(record,self.source,{'#/texts/303'})
        self.assertIn('source_review_relationship_mismatch:#/texts/303',issues)

    def test_bad_explicit_evidence_does_not_fall_back_to_cooccurrence(self):
        from quality_v2 import assess_graph
        g={'nodes':[{'id':'a','label':'Method','name':'WizardCoder'},{'id':'b','label':'Method','name':'StarCoder'}],
           'edges':[{'source':'a','target':'b','label':'BUILT_ON','relationship_evidence':[
               {'source_ref':'#/texts/303','quote':'An invented unsupported quotation.'}]}]}
        assessed,usable,_,_=assess_graph(g,self.source)
        self.assertEqual(assessed['edges'][0]['support_status'],'rejected')
        self.assertFalse(usable['edges'])

    def test_semantic_review_can_withhold_wrong_clause_ownership(self):
        from review_relationships import Review,apply_review
        row={'relationship':self.proposal(),'accepted':True,'reasons':[]}
        review=Review.model_validate({'decisions':[{'candidate_id':'R1','verdict':'unsupported','reason':'The source assigns the data to another model.'}]})
        self.assertFalse(apply_review([row],review)[0]['accepted'])

    def test_semantic_review_cannot_rescue_bad_quotes_or_omit_candidates(self):
        from review_relationships import Review,apply_review
        row={'relationship':self.proposal(),'accepted':False,'reasons':['bad_quote']}
        review=Review.model_validate({'decisions':[{'candidate_id':'R1','verdict':'supported','reason':'Fixture'}]})
        self.assertFalse(apply_review([row],review)[0]['accepted'])
        with self.assertRaisesRegex(ValueError,'omitted'):
            apply_review([row],Review(decisions=[]))


if __name__=='__main__':unittest.main()
