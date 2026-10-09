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

## Render backend

Create a Python 3 Web Service from the repository root on branch `main`.
Commit and push the hosted startup changes before deploying. Use:

- Build Command: `pip install -e ".[gui,docling]"`
- Start Command: `uvicorn pbl_docintel.gui.hosted:create_hosted_app --factory --host 0.0.0.0 --port $PORT --workers 1`
- Health Check Path: `/api/health`
- Persistent disk mount: `/var/data`
- Environment: `SANTIO_WORKSPACE=/var/data`
- Environment: `SANTIO_ALLOWED_ORIGINS=https://YOUR_FRONTEND.vercel.app`
  (comma-separated exact origins if there is more than one).

The factory creates an empty library on the mounted disk. Existing local sample
papers and ignored conversion outputs are not migrated automatically. Upload
papers to the hosted app to populate it, or transfer a complete corpus workspace
to the disk separately. Model caches also default to the workspace disk.
Without `SANTIO_WORKSPACE`, startup uses `./storage`; a persistent disk is required
to preserve files across deployments and restarts.

Render's `RENDER_EXTERNAL_HOSTNAME` is accepted automatically. For custom domains,
set `SANTIO_ALLOWED_HOSTS` to their comma-separated hostnames. Explicitly allowed
frontend origins can make API reads and writes, including through a Vercel rewrite;
other cross-site writes remain rejected. Existing local defaults are unchanged.
Use one service instance and one Uvicorn worker with the current file/job storage.
Service restarts still interrupt running conversion/understanding jobs.

This entrypoint provides hosting configuration, not user authentication or
per-user document isolation. The current application is a shared workspace.

## Vercel frontend build

The root `vercel.json` selects the Vite framework, `npm ci`,
`npm run build:vercel`, and the `dist/vercel` output directory. Keep the Vercel
project Root Directory at the repository root. Commit and push this configuration,
then redeploy the project.

The hosted build uses `/` as its asset base and copies the complete local PDF.js
distribution into `dist/vercel/static/vendor`, including modules, worker, CSS,
fonts, cMaps and WASM. The existing `npm run build` still writes to
`src/pbl_docintel/gui/static/react` with the `/static/react/` base for local Python
serving. To verify the hosted layout locally, run `npm run build:vercel` and
`npx vite preview --config frontend/vite.config.ts --mode vercel`.

This configuration deploys the frontend. It does not start the Python API or
Docling worker. Before using the hosted application's library or uploads:

- Configure `/api` routing to the deployed backend; localhost is not a public API.
  Add a Vercel external rewrite from `/api/:path*` to
  `https://YOUR_BACKEND_HOST/api/:path*` once the real backend URL is available.
  The Vite development proxy is only used by `npm run dev`.
- Set the hosted backend's `SANTIO_ALLOWED_ORIGINS` for the real frontend domain.
  Local startup still accepts only localhost hosts and same-origin writes.
- Add user authentication and document isolation before exposing private uploads.

An alternative is a Vercel FastAPI API that schedules conversion through an
external durable worker and uses persistent remote storage. That is a backend
redesign; Vercel's Python support alone does not supply that architecture.

The repository now contains the frontend deployment configuration. No Vercel
project, production backend URL or credentials have been created, and nothing
has been published by these local changes.

Sources:

- [Vite on Vercel](https://vercel.com/docs/frameworks/frontend/vite)
- [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi)
- [Function runtimes and filesystem support](https://vercel.com/docs/functions/runtimes)
- [Function limits](https://vercel.com/docs/functions/limitations)
