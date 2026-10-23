"""Evaluate a scoped run against a frozen source-backed development reference."""
import argparse
from collections import Counter
import json
from pathlib import Path

from evaluate_v2 import check
from sandbox import write_json


def evaluate(folder,reference):
    folder=Path(folder).resolve();reference=Path(reference).resolve()
    manifest=json.loads((folder/'run.json').read_text(encoding='utf-8'))
    ref=json.loads(reference.read_text(encoding='utf-8'))
    if manifest['input']['source_sha256']!=ref['source_sha256']:
        raise ValueError('Reference and selected document have different source hashes')
    raw=json.loads((folder/'graph.json').read_text(encoding='utf-8'))
    usable=json.loads((folder/'usable_graph.json').read_text(encoding='utf-8'))
    rows=[{**item,'represented':check(raw,item),'source_linked':check(usable,item)} for item in ref['checks']]
    forbidden=[{**item,'present':check(raw,item),'source_linked':check(usable,item)} for item in ref.get('forbidden',[])]
    by_id={n['id']:n for n in raw['nodes']}
    semantic=[e for e in raw['edges'] if by_id[e['source']]['label']!='ResearchPaper']
    report={'reference_version':ref['version'],'reference_note':ref['note'],'source_sha256':ref['source_sha256'],
        'analysis_scope':manifest['analysis_scope'],'batch_statuses':manifest.get('batch_statuses'),
        'nodes':len(raw['nodes']),'edges':len(raw['edges']),'node_types':dict(Counter(n['label'] for n in raw['nodes'])),
        'non_paper_relationships':len(semantic),'non_paper_relation_labels':dict(Counter(e['label'] for e in semantic)),
        'represented':sum(r['represented'] for r in rows),'source_linked':sum(r['source_linked'] for r in rows),
        'total':len(rows),'checks':rows,'forbidden':forbidden,
        'note':'Representation and source-link checks only. A nonempty graph is not evidence of exhaustive or correct semantic relationships.'}
    write_json(folder/'section_evaluation.json',report)
    write_json(folder/'development_reference.json',ref)
    print(json.dumps({k:report[k] for k in ['nodes','edges','non_paper_relationships','represented','source_linked','total','batch_statuses']},indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--reference',type=Path,required=True)
    args=parser.parse_args();evaluate(args.run,args.reference)
