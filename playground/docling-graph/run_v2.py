"""Versioned, source-aware Docling Graph sandbox. No PDF reconversion."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import logging
from pathlib import Path
import re
import sys
from time import perf_counter

from sandbox import HERE, inspect_source, load_connection, write_json


def graph_json(graph):
    return {"nodes":[{"id":i,**d} for i,d in graph.nodes(data=True)],"edges":[{"source":s,"target":t,**d} for s,t,d in graph.edges(data=True)]}


def extraction_is_substantive(graph):
    """A root-only response is an extraction failure, even if JSON validates."""
    return bool(graph['edges']) and any(n.get('label') != 'ResearchPaper' for n in graph['nodes'])


def contract_outcome(events,requested):
    completions=[e['payload'] for e in events if e.get('event_type')=='extraction_completed']
    dense=[p for p in completions if p.get('source_type')=='chunk_batch']
    direct=[p for p in completions if p.get('source_type')=='chunk' and p.get('parsed_model') is not None]
    if dense and not any(p.get('parsed_model') is not None for p in dense) and direct:
        return 'direct_fallback_after_dense_failure'
    if any(p.get('parsed_model') is not None for p in dense):return 'dense'
    if direct:return 'direct'
    return 'unresolved_'+requested


def postprocess(folder, source_path=None):
    from docling_graph.core.converters.graph_converter import GraphConverter
    from quality_v2 import normalize_records, add_table_measurements, assess_graph
    from research_schema_v2 import ResearchPaper
    from source_index import SourceIndex
    from viewer import render_viewer
    manifest=json.loads((folder/'run.json').read_text(encoding='utf-8'))
    source=SourceIndex(source_path or manifest['input']['source'])
    if source.document_id != manifest['input']['source_sha256']:
        raise ValueError('Input changed since this extraction; choose the original source.')
    records=json.loads((folder/'extracted_records.json').read_text(encoding='utf-8'))
    if len(records)!=1:
        raise ValueError('Expected one merged paper record; retain raw output and inspect the extraction.')
    paper,aliases=normalize_records(ResearchPaper.model_validate(records[0]))
    paper,measurements=add_table_measurements(paper,source)
    graph,_=GraphConverter(alias_llm_fn=None).pydantic_list_to_graph([paper])
    raw_graph=graph_json(graph)
    from relationship_pass import attach_edge_evidence,relationship_gate
    proposals=folder/'relationship_candidates.json'
    if proposals.is_file():
        raw_graph=attach_edge_evidence(raw_graph,json.loads(proposals.read_text(encoding='utf-8')))
    assessed,usable,ledger,quality=assess_graph(raw_graph,source)
    chunks=source.chunks()
    source.write(folder,chunks)
    for name,data in [('normalized_records.json',[paper.model_dump(mode='json')]),('graph.json',assessed),
                      ('usable_graph.json',usable),('evidence.json',ledger),('aliases.json',aliases+measurements['aliases']),
                      ('measurements.json',[m.model_dump(mode='json') for e in paper.experiments for m in e.measurements])]:
        write_json(folder/name,data)
    quality.update(measurements=measurements,source=source.inventory(chunks),
        node_types=dict(Counter(n['label'] for n in assessed['nodes'])),
        finding_kinds=dict(Counter(n.get('kind') for n in assessed['nodes'] if n['label']=='Finding')))
    scope=manifest.get('analysis_scope',{})
    selected_refs=set(scope.get('selected_source_refs',[]))
    quality['sections']=[{'headings':c['headings'],'refs':c['refs'],
                          'extraction_status':('extracted_in_selected_scope' if selected_refs&set(c['refs']) else 'not_attempted') if scope.get('partial_document') else 'supplied_to_model',
                          'source_linked_nodes':sum(bool(set(c['refs']) & set(n.get('source_refs',[]))) for n in assessed['nodes'])} for c in chunks]
    if scope:quality['analysis_scope']=scope
    if (folder/'relationship_report.json').is_file():
        quality['relationship_review']=json.loads((folder/'relationship_report.json').read_text(encoding='utf-8'))
    write_json(folder/'quality_report.json',quality)
    render_viewer(assessed,folder/'graph.html')
    render_viewer(usable,folder/'usable_graph.html')
    substantive=extraction_is_substantive(assessed)
    relations=relationship_gate(usable)
    if proposals.is_file() and (folder/'development_reference.json').is_file():
        from relationship_pass import check_development_relationships
        reference=json.loads((folder/'development_reference.json').read_text(encoding='utf-8'))
        if reference['source_sha256']!=source.document_id:
            raise ValueError('Relationship reference source has changed')
        relations=check_development_relationships(usable,reference)
    manifest.update(status=('complete_with_unresolved' if quality['edge_statuses'].get('needs_review') or measurements['unresolved'] else 'complete') if substantive else 'insufficient_extraction',
                    quality_status='source_linked_candidates_not_independently_verified',nodes=len(assessed['nodes']),edges=len(assessed['edges']),
                    usable_nodes=len(usable['nodes']),usable_edges=len(usable['edges']),measurements=measurements['added'],
                    node_types=quality['node_types'],viewer=str(folder/'graph.html'),input_unchanged=True,
                    postprocess_schema_version=__import__('research_schema_v2').SCHEMA_VERSION,
                    record_gate={'passed':substantive},relationship_gate=relations,
                    extraction_gate={'passed':substantive and relations['passed'],
                                     'reason':'Substantive records and source-linked domain candidates; completeness not established.' if substantive and relations['passed'] else
                                              'Missing substantive records or source-linked inter-entity relationships; do not promote as a successful knowledge graph.'})
    if substantive and not relations['passed']:
        manifest['status']='insufficient_relationship_extraction'
    if proposals.is_file() and (folder/'relationship_report.json').is_file():
        review=json.loads((folder/'relationship_report.json').read_text(encoding='utf-8'))
        if not review['review_complete_for_selected_scope']:
            manifest['extraction_gate']['passed']=False
            manifest['extraction_gate']['reason']='Relationship reviews contain unresolved issues; extraction remains partial.'
    if substantive and scope.get('partial_document'):
        manifest['status']='partial_document_extraction'
    write_json(folder/'run.json',manifest)
    from retrieval_v2 import write_understanding
    write_understanding(folder)
    return manifest


def run(args):
    from docling_graph import PipelineConfig,run_pipeline
    from docling_graph.llm_clients.config import resolve_effective_model_config
    from nvidia_client import NvidiaClient
    from research_schema_v2 import ResearchPaper,SCHEMA_VERSION
    info=inspect_source(args.source)
    model,base_url,secret=load_connection(args.model)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder=HERE/'outputs'/f"{re.sub(r'[^a-zA-Z0-9._-]','-',args.source.stem)}-v2-{args.contract}-{stamp}"
    folder.mkdir(parents=True)
    schema=ResearchPaper.model_json_schema()
    schema_hash=hashlib.sha256(json.dumps(schema,sort_keys=True).encode()).hexdigest()
    overrides={'connection':{'base_url':base_url},'generation':{'temperature':0.0,'max_tokens':args.max_output_tokens},
               'reliability':{'timeout_s':args.timeout,'max_retries':args.retries},'context_limit':131072,'max_output_tokens':args.max_output_tokens}
    settings=dict(source=str(args.source.resolve()),template=ResearchPaper,backend='llm',inference='remote',provider_override='openai',
        model_override=f'openai/{model}',llm_overrides=overrides,processing_mode='many-to-one',extraction_contract=args.contract,
        use_chunking=True,chunk_max_tokens=args.chunk_tokens,dense_skeleton_batch_tokens=args.batch_tokens,parallel_workers=1,
        llm_input_format='markdown',structured_output=not args.prompt_json,provenance='detailed',dump_to_disk=True,
        output_dir=str(folder/'artifacts'),debug=True,export_docling=False,gleaning_enabled=not args.skip_gleaning)
    client=NvidiaClient(resolve_effective_model_config('openai',f'openai/{model}',overrides=overrides),thinking=args.thinking,
                         cache_dir=None if args.no_cache else HERE/'outputs'/'cache-v2'/schema_hash,sdk_retries=0)
    manifest=dict(status='running',started_at=datetime.now(timezone.utc).isoformat(),input=info,schema_version=SCHEMA_VERSION,
                  schema_sha256=schema_hash,configuration={**settings,'template':'research_schema_v2.ResearchPaper'},
                  thinking=args.thinking,versions={p:version(p) for p in ['docling-graph','docling-core','pydantic','litellm']},
                  cache_policy='disabled' if args.no_cache else 'exact request/schema cache; hits make no API call')
    write_json(folder/'run.json',manifest);write_json(folder/'schema.json',schema)
    print(f'V2 run: {folder}\nSource: {info["pages"]} pages; PDF conversion skipped.\nContract: {args.contract}; model: {model}',flush=True)
    started=perf_counter()
    try:
        context=run_pipeline(PipelineConfig(**settings,llm_client=client),mode='api')
        trace=getattr(context,'trace_data',None)
        events=[{'event_type':e.event_type,'payload':e.payload} for e in trace.events] if trace else []
        manifest['actual_contract']=contract_outcome(events,args.contract)
        manifest['provider_failures']=sum(c.get('status')=='failed' for c in client.calls)
        write_json(folder/'extracted_records.json',[m.model_dump(mode='json') for m in context.extracted_models or []])
        if context.knowledge_graph is None:
            raise ValueError('Library returned no graph')
        write_json(folder/'native_graph.json',graph_json(context.knowledge_graph))
        write_json(folder/'model_calls.json',client.calls)
        manifest.update(extraction_seconds=round(perf_counter()-started,2))
        write_json(folder/'run.json',manifest)
        final=postprocess(folder,args.source)
        final.update(elapsed_seconds=round(perf_counter()-started,2))
        write_json(folder/'run.json',final)
        if final['extraction_gate']['passed']:
            write_json(HERE/'outputs/latest_v2.json',{'run_dir':str(folder),'viewer':str(folder/'graph.html')})
        from evaluate_v2 import evaluate_run
        evaluate_run(folder)
        print(f"Finished with quality status {final['quality_status']}: {final['nodes']} nodes, {final['edges']} edges; {final['measurements']} grounded measurement cells.\nRun: {folder}",flush=True)
        return 0 if final['extraction_gate']['passed'] else 2
    except (Exception,KeyboardInterrupt) as error:
        manifest.update(status='interrupted' if isinstance(error,KeyboardInterrupt) else 'failed',error_type=type(error).__name__,elapsed_seconds=round(perf_counter()-started,2))
        write_json(folder/'run.json',manifest);write_json(folder/'model_calls.json',client.calls)
        print(f'{type(error).__name__}: {str(error).replace(secret,"[REDACTED]")[:1500]}\nSaved run: {folder}',file=sys.stderr)
        return 130 if isinstance(error,KeyboardInterrupt) else 1


def latest():
    return Path(json.loads((HERE/'outputs/latest_v2.json').read_text(encoding='utf-8'))['run_dir'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='command',required=True)
    run_cmd=subs.add_parser('run')
    run_cmd.add_argument('--source',required=True,type=Path)
    run_cmd.add_argument('--contract',choices=['direct','dense','auto'],default='direct')
    run_cmd.add_argument('--model');run_cmd.add_argument('--thinking',action='store_true');run_cmd.add_argument('--prompt-json',action='store_true')
    run_cmd.add_argument('--no-cache',action='store_true')
    run_cmd.add_argument('--skip-gleaning',action='store_true',help='Skip the optional follow-up model pass')
    run_cmd.add_argument('--retries',type=int,default=0,help='Bounded provider retries; SDK retries are disabled')
    for name,default in [('chunk-tokens',2048),('batch-tokens',8192),('max-output-tokens',16384),('timeout',180)]:
        run_cmd.add_argument('--'+name,type=int,default=default)
    for action in ['postprocess','evaluate','query','serve']:
        cmd=subs.add_parser(action);cmd.add_argument('--run',type=Path)
        if action=='query':
            cmd.add_argument('question');cmd.add_argument('--answer',action='store_true');cmd.add_argument('--text-only',action='store_true')
        if action=='serve':cmd.add_argument('--port',type=int,default=8772)
    args=parser.parse_args()
    if args.command=='run':
        if min(args.chunk_tokens,args.batch_tokens,args.max_output_tokens,args.timeout)<=0:parser.error('Budgets must be positive')
        if args.retries<0:parser.error('Retries cannot be negative')
        return run(args)
    folder=(args.run or latest()).resolve()
    if args.command=='postprocess': print(json.dumps(postprocess(folder),indent=2))
    elif args.command=='evaluate':
        from evaluate_v2 import evaluate_run
        print(json.dumps(evaluate_run(folder),indent=2))
    elif args.command=='query':
        from retrieval_v2 import ResearchWorkspace
        w=ResearchWorkspace(folder);result=w.ask(args.question,use_graph=not args.text_only) if args.answer else w.retrieve(args.question,use_graph=not args.text_only)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    else:
        from server_v2 import serve
        serve(folder,args.port)
    return 0


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    raise SystemExit(main())
