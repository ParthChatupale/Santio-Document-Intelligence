"""Recover a saved dense assembly after a schema repair, without model requests.

The original failed attempt remains untouched. This is a derived artifact,
not a new successful end-to-end dense extraction or a controlled benchmark.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from sandbox import write_json


def recover(origin):
    from research_schema_v2 import ResearchPaper, SCHEMA_VERSION
    from run_v2 import graph_json, postprocess
    from evaluate_v2 import evaluate_run
    from docling_graph.core.converters.graph_converter import GraphConverter
    origin=Path(origin).resolve()
    candidates=list(origin.glob('artifacts/**/dense_assembled_root.json'))
    if len(candidates)!=1:
        raise ValueError('Choose an attempt with exactly one saved dense assembly')
    source=candidates[0]
    raw=source.read_bytes()
    paper=ResearchPaper.model_validate_json(raw)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder=origin.parent/f'{origin.name}-recovered-{stamp}'
    folder.mkdir()
    manifest=json.loads((origin/'run.json').read_text(encoding='utf-8'))
    manifest.update(status='offline_recovery',schema_version=SCHEMA_VERSION,
        recovery={'origin_run':str(origin),'assembly':str(source),'assembly_sha256':hashlib.sha256(raw).hexdigest(),
                  'repair':'Allow identity-only configuration references; method details belong on canonical records.',
                  'api_calls':0,'note':'Derived from a failed dense attempt. This is not a clean end-to-end success or controlled comparison.'},
        actual_contract='dense_saved_assembly_offline_schema_recovery')
    schema=ResearchPaper.model_json_schema()
    manifest['schema_sha256']=hashlib.sha256(json.dumps(schema,sort_keys=True).encode()).hexdigest()
    write_json(folder/'schema.json',schema)
    write_json(folder/'run.json',manifest)
    write_json(folder/'extracted_records.json',[paper.model_dump(mode='json')])
    graph,_=GraphConverter(alias_llm_fn=None).pydantic_list_to_graph([paper])
    write_json(folder/'native_graph.json',graph_json(graph))
    write_json(folder/'model_calls.json',[])
    final=postprocess(folder)
    evaluate_run(folder)
    print(json.dumps({'run_dir':str(folder),'status':final['status'],'nodes':final['nodes'],
                      'edges':final['edges'],'measurements':final['measurements'],'new_api_calls':0},indent=2))
    return folder


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    recover(parser.parse_args().run)
