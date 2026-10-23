"""Trace an existing run offline; optionally make two bounded diagnostic calls.

This does not change the extractor, template, original app or selected demo run.
The two short-excerpt cases hold source/schema/provider settings fixed and vary
only an explicit coverage instruction. They are a diagnostic, not a benchmark.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from sandbox import HERE, load_connection, write_json


def investigate(folder,live=False):
    from docling_core.types.doc import DoclingDocument
    from docling_graph.core.extractors.contracts.direct.prompts import get_extraction_prompt
    from docling_graph.llm_clients.config import resolve_effective_model_config
    from nvidia_client import NvidiaClient
    from research_schema_v2 import ResearchPaper
    folder=Path(folder).resolve()
    manifest=json.loads((folder/'run.json').read_text(encoding='utf-8'))
    schema=json.loads((folder/'schema.json').read_text(encoding='utf-8'))
    schema_text=json.dumps(schema,indent=2)
    source=Path(manifest['input']['source'])
    doc=DoclingDocument.model_validate_json(source.read_bytes())
    markdown=doc.export_to_markdown()
    model,base,_=load_connection()
    settings=manifest['configuration']['llm_overrides']
    # The live cases deliberately reuse this saved provider/model configuration.
    if model!=manifest['configuration']['model_override'].removeprefix('openai/'):
        raise ValueError('Configured model differs from the saved run; an uncontrolled comparison would be misleading')
    client=NvidiaClient(resolve_effective_model_config('openai',f'openai/{model}',overrides=settings),
                        thinking=manifest['thinking'],sdk_retries=0)
    prompt=get_extraction_prompt(markdown,schema_text,structured_output=False,schema_dict=schema,input_format='markdown')
    request=client._build_request(client._prepare_messages(prompt),schema_json=schema_text,structured_output=False)
    keys=('model','messages','temperature','top_p','max_tokens','response_format','extra_body')
    public={k:request[k] for k in keys if k in request}
    digest=hashlib.sha256(json.dumps(public,sort_keys=True,default=str).encode()).hexdigest()
    cached=HERE/'outputs/cache-v2'/manifest['schema_sha256']/f'{digest}.json'
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out=folder/'investigation'/stamp
    out.mkdir(parents=True)
    report={'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'pdf_bytes_sent':False,'input_chain':['saved DoclingDocument JSON','DoclingDocument','export_to_markdown','chat text messages'],
            'markdown_characters':len(markdown),'request_cache_key':digest,'exact_saved_request_match':cached.is_file(),
            'content_types':['text'],'response_format':public.get('response_format'),
            'root_required_fields':schema.get('required'),
            'sparse_recovery':{'structured_output':manifest['configuration']['structured_output'],
                               'gleaning_enabled':manifest['configuration']['gleaning_enabled'],
                               'native_sparse_retry_applies_only_to_structured_mode':True},'cases':[]}
    write_json(out/'reconstructed_request.json',public)
    if cached.is_file():
        data=json.loads(cached.read_text(encoding='utf-8'))
        report['original_raw_response']=data['content']
        report['original_usage']=data['metadata'].get('usage')
    write_json(out/'report.json',report)
    print('Request reconstruction:',json.dumps({k:report[k] for k in ['exact_saved_request_match','markdown_characters','pdf_bytes_sent','root_required_fields']}),flush=True)
    if live:
        chunks=json.loads((folder/'chunks.json').read_text(encoding='utf-8'))
        chosen=[c for c in chunks if any(h in {'2.1. Tokenization','2.3. Attention in LLMs'} for h in c['headings'])]
        if not chosen:raise ValueError('Diagnostic section labels are not present in this input')
        title=json.loads((folder/'extracted_records.json').read_text(encoding='utf-8'))[0]['title']
        excerpt=title+'\n\n'+'\n\n'.join(c['text'] for c in chosen)
        write_json(out/'excerpt_sources.json',chosen)
        base_prompt=get_extraction_prompt(excerpt,schema_text,structured_output=False,schema_dict=schema,input_format='markdown')
        for name,extra in [('short_native_prompt',''),('short_explicit_survey_coverage',
            '\nThis source is a survey excerpt, not a paper introducing a new algorithm. '
            'Extract the methods, techniques and technical concepts DISCUSSED in it even when they are prior work. '
            'Populate the corresponding methods/concepts catalogs with evidence quotations when supported. '
            'Do not reduce an evidenced passage to its paper title. Do not invent experiments, datasets or measurements absent from this excerpt.')]:
            case_prompt={**base_prompt,'system':base_prompt['system']+extra}
            write_json(out/f'{name}.prompt.json',case_prompt)
            try:
                parsed=client.get_json_response(case_prompt,schema_json=schema_text,structured_output=False)
                raw=client.last_call_diagnostics.get('raw_response')
                write_json(out/f'{name}.raw.json',{'raw_response':raw,'parsed_json':parsed})
                validated=ResearchPaper.model_validate(parsed)
                counts={k:len(getattr(validated,k)) for k in ['methods','concepts','datasets','experiments','findings']}
                names=[x.name for k in ['methods','concepts','datasets'] for x in getattr(validated,k)]
                row={'case':name,'source_characters':len(excerpt),'source_refs':[r for c in chosen for r in c['refs']],
                     'valid_schema':True,'catalog_counts':counts,'entity_names':names,'call':client.calls[-1]}
            except Exception as error:
                row={'case':name,'valid_schema':False,'error_type':type(error).__name__,'call':client.calls[-1] if client.calls else None}
            report['cases'].append(row)
            write_json(out/'report.json',report)
            print('Diagnostic result:',json.dumps(row),flush=True)
    write_json(out/'model_calls.json',client.calls)
    print('Investigation saved:',out,flush=True)
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True,type=Path)
    parser.add_argument('--live',action='store_true',help='Make at most two short-excerpt NVIDIA requests; no whole-paper rerun')
    args=parser.parse_args()
    investigate(args.run,args.live)
