"""Combine preserved successful section records offline; no model requests."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path

from sandbox import HERE,write_json


def combine(folders,reference=None):
    from docling_graph.core.converters.graph_converter import GraphConverter
    from research_schema_v2 import ResearchPaper
    from run_sections import merge_sections
    from run_v2 import graph_json,postprocess
    folders=[Path(p).resolve() for p in folders]
    manifests=[json.loads((p/'run.json').read_text(encoding='utf-8')) for p in folders]
    if len({m['input']['source_sha256'] for m in manifests})!=1 or len({m['schema_sha256'] for m in manifests})!=1:
        raise ValueError('Only the same source document and schema can be combined')
    if any(m['status']=='running' for m in manifests):raise ValueError('Wait for all selected runs to finish')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder=HERE/'outputs'/f"{Path(manifests[0]['input']['source']).stem}-sections-combined-{stamp}"
    folder.mkdir()
    models=[];calls=[];batches=[];selected={}
    for origin,manifest in zip(folders,manifests):
        models.extend(ResearchPaper.model_validate_json(p.read_bytes()) for p in sorted(origin.glob('batches/*/validated.json')))
        for call in json.loads((origin/'model_calls.json').read_text(encoding='utf-8')):
            calls.append({**call,'origin_run':str(origin),'origin_request':call['request'],'request':len(calls)+1})
        for batch in manifest['batches']:batches.append({**batch,'origin_run':str(origin),'origin_batch':batch['batch'],'batch':len(batches)+1})
        for c in json.loads((origin/'selected_chunks.json').read_text(encoding='utf-8')):selected[c['id']]=c
    covered={ref for b in batches if b['status']=='extracted' for ref in b['refs']}
    for b in batches:
        if b['status']!='extracted' and set(b['refs'])<=covered:
            b['prior_status']=b['status'];b['status']='recovered_by_smaller_batches'
    manifest={**manifests[0],'status':'offline_combination','started_at':datetime.now(timezone.utc).isoformat(),
        'actual_contract':'section_scoped_native_direct_then_offline_identity_merge',
        'origin_runs':[str(p) for p in folders],'new_model_calls':0,'batches':batches,
        'analysis_scope':{'partial_document':True,'selected_chunks':len(selected),
            'total_chunks':manifests[0]['analysis_scope']['total_chunks'],
            'requested_headings':list(dict.fromkeys(h for m in manifests for h in m['analysis_scope']['requested_headings'])),
            'planned_batches':len(batches),'selected_source_refs':sorted({r for c in selected.values() for r in c['refs']})},
        'batch_statuses':dict(Counter(b['status'] for b in batches)),
        'token_usage':{'input':sum(c.get('usage',{}).get('prompt_tokens',0) for c in calls),
            'output':sum(c.get('usage',{}).get('completion_tokens',0) for c in calls),
            'incomplete_due_to_failed_requests':any(c['status']=='failed' for c in calls)},
        'provider_failures':sum(c['status']=='failed' for c in calls),
        'elapsed_seconds':sum(m.get('elapsed_seconds',0) for m in manifests),
        'timing_note':'Sum of recorded active run/recovery durations; excludes time developing between attempts.',
        'latest_pointer_updated':False}
    merged=merge_sections(models)
    write_json(folder/'run.json',manifest)
    write_json(folder/'schema.json',ResearchPaper.model_json_schema())
    write_json(folder/'section_records.json',[m.model_dump(mode='json') for m in models])
    write_json(folder/'extracted_records.json',[merged.model_dump(mode='json')])
    write_json(folder/'model_calls.json',calls);write_json(folder/'selected_chunks.json',list(selected.values()))
    graph,_=GraphConverter(alias_llm_fn=None).pydantic_list_to_graph([merged])
    write_json(folder/'native_graph.json',graph_json(graph))
    final=postprocess(folder)
    quality=json.loads((folder/'quality_report.json').read_text(encoding='utf-8'))
    for section in quality['sections']:
        matched=[b for b in batches if set(b['refs'])&set(section['refs'])]
        section['extraction_status']='not_attempted' if not matched else 'extracted' if any(b['status']=='extracted' for b in matched) else matched[0]['status']
    quality['analysis_scope']=manifest['analysis_scope'];write_json(folder/'quality_report.json',quality)
    final['status']='partial_document_extraction'
    write_json(folder/'run.json',final)
    if reference:
        from evaluate_sections import evaluate
        evaluation=evaluate(folder,reference)
        final['relationship_extraction_status']='missing_non_paper_relations' if not evaluation['non_paper_relationships'] else 'candidates_require_semantic_review'
        write_json(folder/'run.json',final)
    write_json(HERE/'outputs/latest_sections_trial.json',{'run_dir':str(folder),'status':final['status'],
        'relationship_extraction_status':final.get('relationship_extraction_status'),'note':'A trial artifact; does not replace latest_v2 or the original app.'})
    print('Combined trial:',folder,flush=True)
    return folder


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='append',required=True,type=Path);parser.add_argument('--reference',type=Path)
    args=parser.parse_args();combine(args.run,args.reference)
