"""Local evidence workspace over a completed sandbox run; extraction is explicit."""
from pathlib import Path


def create_app(folder):
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse
    from pydantic import BaseModel, Field
    from retrieval_v2 import ResearchWorkspace
    from sandbox import ROOT, load_connection
    folder=Path(folder).resolve()
    workspace=ResearchWorkspace(folder)
    app=FastAPI(title='Santio research sandbox v2')
    class Question(BaseModel):
        question: str = Field(min_length=1,max_length=6000)
        use_graph: bool = True

    @app.get('/')
    def home():return FileResponse(Path(__file__).with_name('workspace_v2.html'))

    @app.get('/api/overview')
    def overview():
        import json
        workspace.refresh()
        return {'understanding':json.loads((folder/'understanding.json').read_text(encoding='utf-8')),
                'run':workspace.manifest,'quality':json.loads((folder/'quality_report.json').read_text(encoding='utf-8'))}

    @app.get('/api/graph')
    def graph():
        workspace.refresh()
        return workspace.graph

    @app.get('/api/evidence')
    def evidence(ref:str):
        unit=workspace.source['units'].get(ref)
        if unit is None:raise HTTPException(404,'Source reference not found')
        return unit

    @app.get('/api/retrieve')
    def retrieve(question:str,use_graph:bool=True):
        try:return workspace.retrieve(question,use_graph=use_graph)
        except ValueError as error:raise HTTPException(400,str(error)) from None

    @app.post('/api/ask')
    def ask(body:Question):
        try:return workspace.ask(body.question,use_graph=body.use_graph)
        except Exception as error:
            try:secret=load_connection()[2]
            except Exception:secret=''
            message=str(error).replace(secret,'[REDACTED]') if secret else type(error).__name__
            raise HTTPException(502,message[:500]) from None

    @app.get('/graph.html')
    def graph_view():return FileResponse(folder/'usable_graph.html')

    @app.get('/raw-graph.html')
    def raw_graph():return FileResponse(folder/'graph.html')

    @app.get('/pdf')
    def pdf():
        # Untrusted origin filenames cannot escape the explicitly selected workspace.
        name=Path(workspace.source['document']['source_filename']).name
        candidates=[ROOT/name,Path(workspace.manifest['input']['source']).parent/name]
        path=next((p for p in candidates if p.is_file() and p.suffix.lower()=='.pdf'),None)
        if path is None:raise HTTPException(404,'Original PDF is not available beside this workspace or source JSON')
        return FileResponse(path,media_type='application/pdf',content_disposition_type='inline')
    return app


def serve(folder,port=8772):
    import uvicorn
    print(f'Research workspace: http://127.0.0.1:{port}\nUsing saved run: {folder}\nModel calls occur only when you submit Ask.',flush=True)
    uvicorn.run(create_app(folder),host='127.0.0.1',port=port)
