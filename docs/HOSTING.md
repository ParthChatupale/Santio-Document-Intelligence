# Hosting status

Checked 9 October 2026 against the current Vercel documentation.

The application has a working Python/FastAPI backend: paper/evidence/PDF/export
routes and persistent local upload/conversion jobs. It is currently configured
for a local workspace, not a deployed multi-user service.

The whole repository cannot be deployed unchanged to Vercel. Vercel supports
both Vite and FastAPI, but its Functions use a read-only application filesystem
with writable temporary scratch space. Our service initializes job files in
`data/import-jobs`, writes uploads/conversions under `data/uploads`, registers
documents in `data/gui-library.json`, and manages a thread queue and a Docling
subprocess after the upload response. Temporary files and a function's local
process state are not our durable library/job store. Invocation, payload and
bundle limits also apply; a hosted upload path must be designed around them.

## Practical deployment direction

For a first hosted version, deploy the React frontend on Vercel and run the
FastAPI service/Docling converter on a persistent server. Keep persistent storage
for uploaded PDFs, conversions and job records. For multiple workers/users,
move job metadata to a database and conversion scheduling to a durable queue;
object storage can hold PDFs and outputs.

Before deploying the frontend:

- Adjust Vite's production base/output settings for the chosen Vercel layout.
  The current build deliberately uses `/static/react/` for Python static serving.
- Configure `/api` routing to the deployed backend; localhost is not a public API.
- Serve or proxy the local PDF.js module, worker, fonts, cMaps and WASM resources.
- Configure backend allowed hosts/origins for the real domain. The current
  service only accepts localhost hosts and same-origin writes.
- Add user authentication and document isolation before exposing private uploads.

An alternative is a Vercel FastAPI API that schedules conversion through an
external durable worker and uses persistent remote storage. That is a backend
redesign; Vercel's Python support alone does not supply that architecture.

No Vercel project, production backend URL, credentials or deployment configuration
has been created. Nothing has been published by this hosting assessment.

Sources:

- [Vite on Vercel](https://vercel.com/docs/frameworks/frontend/vite)
- [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi)
- [Function runtimes and filesystem support](https://vercel.com/docs/functions/runtimes)
- [Function limits](https://vercel.com/docs/functions/limitations)
