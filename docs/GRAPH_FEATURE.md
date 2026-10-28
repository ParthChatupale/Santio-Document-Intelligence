# Optional Microsoft GraphRAG view

Open a paper in Santio and select **Graph**. The existing Explore, Ask, Review,
Compare, upload and PDF flows remain separate. The regular Ask tab continues to
use the existing vector RAG. Graph questions use Microsoft's native Local,
Basic or Global query mode inside the Graph view.

The initial registered artifact is **Tetris3D (`arxiv:2610.10539v1`)**, 632 nodes
and 801 merged edges. It retains isolated entities and source-review flags.
Processing passed replay and coverage checks, but semantic quality remains
mixed; it is explicitly experimental. A larger graph is not an accuracy claim.

Other papers display “No graph prepared for this paper.” Uploading a PDF does
not automatically trigger a costly graph build. This integration publishes the
completed tested artifact, not a general graph-indexing job UI.

## Isolation and locations

- `frontend/src/GraphPanel.tsx`: optional, lazily loaded paper-specific tab.
- `src/pbl_docintel/gui/graphs.py`: registry validation, paper-scoped routes and
  owned worker lifecycle. No native GraphRAG imports in the main API process.
- `src/pbl_docintel/gui/graph_runtime/`: promoted, app-owned query runtime and
  renderer. It imports no playground scripts and connects to no sandbox port.
- `data/graph-rag/artifacts/`: copied native tables, vectors, evidence and review.
- `data/graph-rag/registry.json`: explicitly maps a paper ID and PDF SHA-256 to
  its graph version. Changed PDFs cannot silently reuse a different graph.
- Graph questions and traces live inside the registered artifact's `queries/`;
  existing vector-question history stays under `data/question-jobs/`.
- Worker startup logs are under `data/graph-rag/workers/` and per-question
  provider traces are in `queries/web-*/`. They do not contain API keys.

The browser's graph requests stay on the main website, beneath
`/api/papers/{paper_id}/graph/view/`. The iframe scopes renderer styles and DOM
to this feature. It is not a security boundary against the app's own trusted
code. Only its view route permits same-origin framing; other routes retain the
existing `frame-ancestors 'none'` policy.

A private worker starts only when an available graph is opened. It binds a
dynamic loopback port and stops with the main backend, including its owned query
and embedding subprocesses. The main environment still runs FastAPI; the worker
uses the compatible GraphRAG Python environment. The current registration reuses
the already installed Python 3.13 environment in the graph sandbox **as an
interpreter only**. Runtime code and artifacts are app-owned copies. This
interpreter path can be replaced in the registry or `SANTIO_GRAPH_PYTHON` without
changing application code. Its dependencies are pinned in
`src/pbl_docintel/gui/graph_runtime/requirements.txt`.

Embeddings continue to use the cached local Granite model through the main
environment. Answer credentials come from the existing project `.env`; no keys
are copied into the frontend, registry or graph artifact.

## Publish another completed artifact

Run from the workspace with a reviewed, completed run and the matching paper:

```powershell
.\.venv\Scripts\python.exe scripts\register_graph.py PATH_TO_COMPLETED_RUN --paper-id PAPER_ID --graph-python PATH_TO_GRAPHRAG_PYTHON
```

The command checks completion, source integrity, matching PDF, native replay and
the presence of review findings, then copies the artifact and registers it.
These checks do not certify semantic accuracy. Existing registered versions are
not overwritten. Playground question history is not copied.

Start Santio with the existing `npm run dev` command; no separate graph-server
command is needed. The original sandbox at port 8775 can remain open independently.
For the agent-restarted current dev session, stdout and stderr are saved in
`data/graph-rag/dev.stdout.log` and `dev.stderr.log`.
