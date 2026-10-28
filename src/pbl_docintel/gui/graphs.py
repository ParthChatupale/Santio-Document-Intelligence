"""Optional per-paper graph feature. No native GraphRAG imports in the main API.

Registered artifacts and query histories are separate from vector RAG. A private
loopback worker starts lazily, using the compatible GraphRAG interpreter. The
browser only talks to the main app's paper-scoped routes.
"""
import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import RLock
from time import monotonic, sleep
import uuid

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool


class Graphs:
    def __init__(self, workspace):
        self.workspace = workspace
        self.base = workspace.root / 'data/graph-rag'
        self.runtime = Path(__file__).with_name('graph_runtime')
        self.workers = {}
        self.lock = RLock()
        self.hashes = {}

    def _entry(self, paper_id):
        if paper_id not in self.workspace.papers:
            raise KeyError('Paper not found')
        registry = self.base / 'registry.json'
        data = json.loads(registry.read_text(encoding='utf-8')) if registry.exists() else {}
        entry = data.get('papers', {}).get(paper_id)
        if not entry:
            return None
        run = (self.workspace.root / entry['run']).resolve()
        if not run.is_relative_to((self.base / 'artifacts').resolve()):
            raise ValueError('Registered graph must be inside the graph artifact directory.')
        paper = self.workspace.papers[paper_id]
        pdf = self.workspace.path(paper['source_pdf'])
        from .server import fingerprint
        stat = pdf.stat()
        signature = (str(pdf), stat.st_mtime_ns, stat.st_size)
        with self.lock:
            if signature not in self.hashes:
                self.hashes[signature] = fingerprint(pdf)
            if self.hashes[signature] != entry['pdf_sha256']:
                raise ValueError('This graph belongs to a different PDF version.')
        manifest = json.loads((run / 'run.json').read_text(encoding='utf-8'))
        coverage = json.loads((run / 'coverage.json').read_text(encoding='utf-8'))
        if manifest['status'] != 'completed' or not coverage.get('processing_complete'):
            raise ValueError('The registered graph has not completed processing.')
        if manifest['source_sha256'] != entry['docling_sha256']:
            raise ValueError('Registered graph provenance does not match its extraction.')
        return data, entry, run, pdf, manifest

    def status(self, paper_id):
        found = self._entry(paper_id)
        if not found:
            return {'status': 'not_prepared', 'available': False,
                    'message': 'No knowledge graph has been prepared for this paper. Explore and Ask remain available.'}
        data, entry, _, _, manifest = found
        python = Path(os.environ.get('SANTIO_GRAPH_PYTHON') or data.get('python', ''))
        if not python.is_file():
            return {'status': 'unavailable', 'available': False,
                    'message': 'The GraphRAG Python environment is unavailable. Check SANTIO_GRAPH_PYTHON.'}
        counts = manifest.get('native_tables', {})
        return {'status': 'ready', 'available': True, 'run_name': entry['run_name'],
                'entities': counts.get('entities', 0), 'edges': counts.get('relationships', 0),
                'experimental': True, 'quality_verified': False}

    def _worker(self, paper_id):
        found = self._entry(paper_id)
        if not found:
            raise ValueError('No graph is registered for this paper.')
        data, entry, run, pdf, _ = found
        with self.lock:
            old = self.workers.get(paper_id)
            identity = (str(run), entry['pdf_sha256'])
            if old and old['process'].poll() is None and old['identity'] == identity:
                return old['port']
            if old:
                self._stop(old['process'])
            python = Path(os.environ.get('SANTIO_GRAPH_PYTHON') or data.get('python', ''))
            if not python.is_file():
                raise ValueError('The GraphRAG Python environment is unavailable.')
            directory = self.base / 'workers'
            directory.mkdir(parents=True, exist_ok=True)
            ident = uuid.uuid4().hex
            ready, log = directory / (ident + '.ready.json'), directory / (ident + '.log')
            env = {**os.environ, 'SANTIO_WORKSPACE': str(self.workspace.root),
                   'SANTIO_DOCUMENT_PYTHON': sys.executable, 'PYTHONIOENCODING': 'utf-8'}
            with log.open('w', encoding='utf-8') as output:
                process = subprocess.Popen([str(python), '-u', str(self.runtime / 'serve.py'),
                    str(run), '--pdf', str(pdf), '--port', '0', '--ready-file', str(ready)],
                    cwd=self.workspace.root, env=env, stdout=output, stderr=output,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.workers[paper_id] = {'process': process, 'identity': identity, 'port': None}
            deadline = monotonic() + 12
            while monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('The graph worker could not start. Check data/graph-rag/workers logs.')
                if ready.exists():
                    port = json.loads(ready.read_text(encoding='utf-8'))['port']
                    self.workers[paper_id]['port'] = port
                    return port
                sleep(.1)
            self._stop(process)
            raise RuntimeError('The graph worker did not become ready. Retry the Graph tab.')

    def proxy(self, paper_id, asset, query='', method='GET', body=None, session=''):
        allowed = {'', 'explorer.js', 'explorer.css', 'graph-geometry.js',
                   'api/status', 'api/graph', 'api/validation', 'api/source',
                   'api/history', 'api/page'}
        if method == 'POST':
            valid = asset == 'api/questions'
        else:
            valid = asset in allowed or bool(re.fullmatch(r'api/jobs/\d{8}T\d{12}Z', asset))
        if not valid:
            raise KeyError('Unknown graph resource')
        port = self._worker(paper_id)
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=20)
        try:
            headers = {'X-Graph-Session': session, 'Content-Type': 'application/json'}
            connection.request(method, '/' + asset + ('?' + query if query else ''), body=body, headers=headers)
            response = connection.getresponse()
            return response.status, response.read(), response.getheader('Content-Type', 'application/json')
        finally:
            connection.close()

    @staticmethod
    def _stop(process):
        if process.poll() is not None:
            return
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    def close(self):
        with self.lock:
            for worker in self.workers.values():
                self._stop(worker['process'])
            self.workers.clear()


def attach_graph_routes(app, graphs, same_origin):
    @app.get('/api/papers/{paper_id}/graph')
    def graph_status(paper_id: str):
        try:
            return graphs.status(paper_id)
        except KeyError as error:
            raise HTTPException(404, str(error)) from None
        except (ValueError, OSError) as error:
            return JSONResponse({'status': 'unavailable', 'available': False, 'message': str(error)})

    @app.api_route('/api/papers/{paper_id}/graph/view/{asset:path}', methods=['GET', 'POST'])
    async def graph_view(paper_id: str, asset: str, request: Request):
        try:
            if request.method == 'POST':
                same_origin(request)
                length = int(request.headers.get('content-length', '0'))
                if not 0 < length <= 32000:
                    raise HTTPException(400, 'Invalid graph question size.')
                body = await request.body()
                if len(body) > 32000:
                    raise HTTPException(400, 'Invalid graph question size.')
            else:
                body = None
            if asset == 'pdf' and request.method == 'GET':
                found = graphs._entry(paper_id)
                if not found:
                    raise KeyError('No graph for this paper')
                return FileResponse(found[3], media_type='application/pdf')
            status, content, content_type = await run_in_threadpool(graphs.proxy, paper_id,
                asset, request.url.query, request.method, body, request.headers.get('x-graph-session', ''))
            return Response(content, status_code=status, headers={'Content-Type': content_type,
                            'Cache-Control': 'no-store'})
        except KeyError as error:
            raise HTTPException(404, str(error)) from None
        except (ValueError, OSError, RuntimeError, http.client.HTTPException) as error:
            raise HTTPException(503, str(error)) from None
