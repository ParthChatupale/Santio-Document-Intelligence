"""Retry one empty/failed section within its original run's API budget.

Successful section files and original attempts remain preserved. No successful
batch is sent again and the main app/latest-run pointer is never changed.
"""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

from sandbox import load_connection,write_json


def retry(folder,batch_number):
    from docling_graph.core.extractors.backends.llm_backend import LlmBackend
    from docling_graph.core.converters.graph_converter import GraphConverter
    from docling_graph.llm_clients.config import resolve_effective_model_config
    from nvidia_client import NvidiaClient
    from research_schema_v2 import ResearchPaper
    from run_sections import merge_sections,SECTION_RULES,CONCISE_RULES
    from run_v2 import postprocess,graph_json
    folder=Path(folder).resolve();manifest=json.loads((folder/'run.json').read_text(encoding='utf-8'))
    if manifest['status']=='running':raise ValueError('Wait for the current extraction process to finish before retrying a batch')
    config=manifest['configuration'];calls=json.loads((folder/'model_calls.json').read_text(encoding='utf-8'))
    if hashlib.sha256(Path(manifest['input']['source']).read_bytes()).hexdigest()!=manifest['input']['source_sha256']:
        raise ValueError('The saved Docling source changed; no request made')
    if len(calls)>=config['max_calls']:raise ValueError('Original call budget is exhausted; no request made')
    row=next(b for b in manifest['batches'] if b['batch']==batch_number)
    if row['status']=='extracted':raise ValueError('This batch already succeeded; no request made')
    batch_dir=folder/'batches'/f'{batch_number:03d}'
    original=next(iter(sorted(batch_dir.glob('prompt-*.json'))))
    prompt=json.loads(original.read_text(encoding='utf-8'))
    body=prompt['user'].split('=== DOCUMENT PAGE ===\n',1)[1].split('\n=== END DOCUMENT PAGE ===',1)[0]
    model,base,secret=load_connection()
    if model!=config['model'] or base!=config['base_url']:raise ValueError('Configured connection changed; an uncontrolled retry is not allowed')
    overrides={'connection':{'base_url':base},'generation':{'temperature':0,'max_tokens':4096},
        'reliability':{'timeout_s':config['timeout'],'max_retries':0},'context_limit':131072,'max_output_tokens':4096}
    class RetryClient(NvidiaClient):
        def get_json_response(self,prompt,**kwargs):
            p={**prompt,'system':prompt['system']+SECTION_RULES+CONCISE_RULES}
            write_json(batch_dir/f'prompt-{len(self.calls)+1}.json',p)
            value=super().get_json_response(p,**kwargs)
            write_json(batch_dir/f'response-{len(self.calls)}.json',{'raw':self.last_call_diagnostics.get('raw_response'),'parsed':value})
            return value
    client=RetryClient(resolve_effective_model_config('openai',f'openai/{model}',overrides=overrides),
        thinking=False,sdk_retries=0,max_calls=config['max_calls'])
    client.calls=calls
    backend=LlmBackend(client,structured_output=False,dense_config={'gleaning_enabled':False,'retry_on_truncation':False})
    before=len(calls);started=perf_counter()
    print(f'Retrying batch {batch_number}: {row["heading"]}; {config["max_calls"]-before} requests remain in the original budget.',flush=True)
    record=backend.extract_from_markdown(body,ResearchPaper,context=f'section {batch_number} recovery',is_partial=True,allow_dense=False)
    new=client.calls[before:]
    row.setdefault('attempt_history',[]).append({k:v for k,v in row.items() if k!='attempt_history'})
    row.update(retried_at=datetime.now(timezone.utc).isoformat(),retry_seconds=round(perf_counter()-started,2),
        call_numbers=row.get('call_numbers',[])+[c['request'] for c in new],
        retry_input_tokens=sum(c.get('usage',{}).get('prompt_tokens',0) for c in new),
        retry_output_tokens=sum(c.get('usage',{}).get('completion_tokens',0) for c in new),retry_max_output_tokens=4096)
    if any(c.get('finish_reason')=='length' for c in new):row['status']='truncated';record=None
    elif record is None:row['status']='failed'
    elif not any(getattr(record,k) for k in ['methods','datasets','concepts','experiments','findings','limitations']):row['status']='empty';record=None
    else:row['status']='extracted'
    if record is not None:
        existing=json.loads(next(folder.glob('batches/*/validated.json')).read_text(encoding='utf-8'))
        record.title=existing['title']
        write_json(batch_dir/'validated.json',record.model_dump(mode='json'))
        row['catalog_counts']={k:len(getattr(record,k)) for k in ['methods','datasets','concepts','experiments','findings','limitations']}
    write_json(folder/'model_calls.json',client.calls);write_json(folder/'run.json',manifest)
    models=[ResearchPaper.model_validate_json(p.read_bytes()) for p in sorted(folder.glob('batches/*/validated.json'))]
    if models:
        merged=merge_sections(models);write_json(folder/'section_records.json',[m.model_dump(mode='json') for m in models])
        write_json(folder/'extracted_records.json',[merged.model_dump(mode='json')])
        graph,_=GraphConverter(alias_llm_fn=None).pydantic_list_to_graph([merged])
        write_json(folder/'native_graph.json',graph_json(graph))
        final=postprocess(folder)
        quality=json.loads((folder/'quality_report.json').read_text(encoding='utf-8'))
        for section in quality['sections']:
            matches=[b for b in manifest['batches'] if set(b['refs'])&set(section['refs'])]
            section['extraction_status']='not_attempted' if not matches else 'extracted' if any(b['status']=='extracted' for b in matches) else matches[0]['status']
        quality['analysis_scope']=manifest['analysis_scope'];write_json(folder/'quality_report.json',quality)
        final.update(status='partial_document_extraction',batch_statuses=dict(Counter(b['status'] for b in manifest['batches'])),
            elapsed_seconds=round(manifest.get('elapsed_seconds',0)+perf_counter()-started,2),
            token_usage={'input':sum(c.get('usage',{}).get('prompt_tokens',0) for c in client.calls),
                         'output':sum(c.get('usage',{}).get('completion_tokens',0) for c in client.calls),
                         'incomplete_due_to_failed_requests':any(c['status']=='failed' for c in client.calls)},
            provider_failures=sum(c['status']=='failed' for c in client.calls))
        write_json(folder/'run.json',final)
    print(json.dumps({'batch':batch_number,'status':row['status'],'new_calls':len(new),'input':row['retry_input_tokens'],'output':row['retry_output_tokens'],'catalog_counts':row.get('catalog_counts')},indent=2),flush=True)
    return 0 if row['status']=='extracted' else 2


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True,type=Path);parser.add_argument('--batch',required=True,type=int)
    args=parser.parse_args()
    raise SystemExit(retry(args.run,args.batch))
