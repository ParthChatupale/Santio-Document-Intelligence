"""Representation/regression and retrieval checks; never a truth-score claim."""
import json
from pathlib import Path
from source_index import normalized


def check(graph, item):
    nodes=graph['nodes'];lookup={n['id']:n for n in nodes}
    if item['kind']=='node':return any(n['label']==item['type'] and normalized(n.get('name',''))==normalized(item['name']) for n in nodes)
    if item['kind']=='edge':return any(e['label']==item['relation'] and normalized(lookup[e['source']].get('name',''))==normalized(item['source']) and normalized(lookup[e['target']].get('name',''))==normalized(item['target']) for e in graph['edges'])
    if item['kind']=='measurement':return any(n['label']=='Measurement' and n.get('table_label')==item['table'] and n.get('row_label')==item['row'] and normalized(n.get('column_label',''))==normalized(item['metric']) and n.get('reported_value')==item['value'] for n in nodes)
    if item['kind']=='finding':return any(n['label']=='Finding' and n.get('kind')==item['finding_kind'] and all(w in normalized(n.get('statement','')) for w in item['words']) for n in nodes)
    raise ValueError('Unknown reference check')


def evaluate_run(folder):
    folder=Path(folder)
    ref=json.loads((Path(__file__).parent/'evaluation/reference.json').read_text(encoding='utf-8'))
    manifest=json.loads((folder/'run.json').read_text(encoding='utf-8'))
    if manifest['input']['source_sha256']!=ref['source_sha256']:
        result={'status':'no_matching_reference','note':'This paper is outside the development reference. No accuracy or coverage score inferred.'}
    else:
        graph=json.loads((folder/'graph.json').read_text(encoding='utf-8'));usable=json.loads((folder/'usable_graph.json').read_text(encoding='utf-8'))
        rows=[{**item,'represented':check(graph,item),'in_source_linked_graph':check(usable,item)} for item in ref['checks']]
        from retrieval_v2 import ResearchWorkspace
        workspace=ResearchWorkspace(folder);retrieval=[]
        for q in ref['retrieval_questions']:
            outcome={**q}
            for mode in [False,True]:
                bundle=workspace.retrieve(q['question'],use_graph=mode)
                refs={r for s in bundle['sources'] for r in s['refs']}
                outcome['graph_plus_chunks' if mode else 'chunks_only']={'expected_source_found':bool(refs & set(q['expected_refs'])),'retrieved_refs':sorted(refs)}
            retrieval.append(outcome)
        result={'status':'development_regression','reference_version':ref['version'],'checks':rows,'represented':sum(x['represented'] for x in rows),
                'source_linked':sum(x['in_source_linked_graph'] for x in rows),'total':len(rows),'retrieval':retrieval,
                'note':'Representation checks and source retrieval only; not independent semantic accuracy, exhaustive recall or answer quality.'}
    (folder/'evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
