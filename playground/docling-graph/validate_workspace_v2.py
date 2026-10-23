"""Explicit local-server smoke check. --live submits three NVIDIA requests."""
import argparse
import json
from pathlib import Path
import httpx


def validate(base_url,live=False):
    report={'server':base_url,'live_model_test':live,'http':[],'answers':[]}
    with httpx.Client(base_url=base_url,timeout=75) as client:
        overview=client.get('/api/overview').raise_for_status().json()
        folder=Path(overview['run']['viewer']).parent
        for route,status in [('/',200),('/api/graph',200),('/api/evidence?ref=missing',404),('/graph.html',200),('/pdf',200)]:
            r=client.get(route)
            report['http'].append({'route':route,'expected':status,'actual':r.status_code,'passed':r.status_code==status})
        if live:
            cases=[('What are the penetration depth (PD) values for Full model (Ours) and w/o Interaction Cond. in Table 3?','values'),
                   ('What limitations does the paper state about physical guarantees and errors propagating through the generation process?','limitations'),
                   ('What is the warranty period offered for purchasing Tetris3D software?','absent')]
            for question,kind in cases:
                r=client.post('/api/ask',json={'question':question,'use_graph':True})
                r.raise_for_status();data=r.json();answer=data['answer']
                passed=(data.get('answer_status')=='insufficient_evidence' if kind=='absent' else
                        all(v in answer for v in ['0.0192','0.4980']) and '[S' in answer if kind=='values' else
                        'guarantee' in answer.lower() and 'error' in answer.lower() and '[S' in answer)
                report['answers'].append({'question':question,'answer':answer,'answer_status':data.get('answer_status'),
                    'model':data.get('model'),'sources':[{'citation':s['citation'],'pages':s['pages'],'refs':s['refs']} for s in data['sources']],
                    'passed':passed,'note':'A few development smoke cases, not independent answer accuracy.'})
                print(kind,'PASS' if passed else 'FAIL',answer,flush=True)
        report['passed']=all(x['passed'] for group in ['http','answers'] for x in report[group])
        (folder/'workspace_smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Saved smoke report:',folder/'workspace_smoke.json',flush=True)
    return report['passed']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8772')
    parser.add_argument('--live',action='store_true')
    args=parser.parse_args()
    raise SystemExit(0 if validate(args.url,args.live) else 1)
