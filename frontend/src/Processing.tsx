import type { Job } from './types';
export interface Transfer {loaded: number; total: number; error?: string}
export const active = (status: string) => ['uploading','queued','processing','cancelling'].includes(status);
export function Processing({id, jobs, loaded, transfer, openJob, openPaper, back, retry, cancel, add}: {
  id: string; jobs: Job[]; loaded: boolean; transfer?: Transfer;
  openJob(id: string): void; openPaper(id: string, ask?: boolean): void; back(): void;
  retry(id: string): void; cancel(id: string): void; add(): void;
}) {
  const job = jobs.find(j => j.job_id === id);
  const completed = job?.completed_stages || (job?.status === 'completed' ? ['upload','extract'] : []);
  const extractionOnly = job?.status === 'completed' && !completed.includes('embed');
  return <main className="processing-page"><button className="source-link" onClick={back}>← Paper library</button>
    <div className="eyebrow">YOUR IMPORTS</div><h1>{id === 'all' ? 'Preparing your research.' : job?.title || 'Preparing your paper.'}</h1>
    {id === 'all' ? <div className="import-cards">{jobs.map(j => <button className="import-card" key={j.job_id} onClick={() => openJob(j.job_id)}><strong>{j.title}</strong><span>{j.stage}</span><small>{j.filename}</small></button>)}{!jobs.length && <p>No imports yet.</p>}</div> : !job ? <p role="status">{loaded ? 'This import was not found.' : 'Loading saved progress…'}</p> : <>
      <p className="muted">{job.filename}{job.size_bytes ? ` · ${(job.size_bytes / 1048576).toFixed(1)} MB` : ''}</p>
      <div className="progress-card"><h2 role="status">{active(job.status) && <span className="spinner"/>} {job.stage}</h2>
        <ol className="processing-steps">{[['upload','Upload PDF'],['extract','Extract with Docling'],['chunk','Prepare contextual passages'],['embed','Create search index']].map(([phase,label]) => <li key={phase} className={completed.includes(phase) ? 'complete' : job.phase === phase ? 'current' : ''}><span>{completed.includes(phase) ? '✓' : '○'}</span>{label}</li>)}</ol>
        {extractionOnly && <p className="notice">This earlier import saved extraction only. Open Ask to prepare its search index.</p>}
        {job.status === 'uploading' && <div>{transfer ? <><progress aria-label="PDF upload" max={transfer.total || 1} value={transfer.loaded}/><p>{transfer.loaded >= transfer.total ? 'Confirming upload with the server…' : `${Math.round(transfer.loaded / transfer.total * 100)}% uploaded`}</p></> : <p>Waiting for the file transfer. If this page was refreshed before upload finished, cancel and choose the PDF again.</p>}</div>}
        {job.phase === 'embed' && active(job.status) && job.total ? <><progress aria-label="Passages embedded" max={job.total} value={job.done || 0}/><p>{job.done || 0} of {job.total} passages embedded</p></> : null}
        {job.conversion_status === 'partial_success' && <p className="notice">Docling reported a partial conversion. Some content may be missing.</p>}
        {(job.error || transfer?.error) && <p className="error" role="alert">{job.error || transfer?.error}</p>}
        <div className="processing-actions">{active(job.status) ? <button className="secondary" onClick={() => cancel(job.job_id)}>Cancel</button> : job.status !== 'completed' ? job.completed_stages?.includes('upload') ? <button className="primary" onClick={() => retry(job.job_id)}>Retry preparation</button> : <button className="primary" onClick={add}>Choose PDF again</button> : null}
          {job.paper_id && <button className="secondary" onClick={() => openPaper(job.paper_id!)}>Read extracted paper</button>}
          {job.status === 'completed' && job.paper_id && <button className="primary" onClick={() => openPaper(job.paper_id!, true)}>{extractionOnly ? 'Prepare for questions →' : 'Ask this paper →'}</button>}</div>
      </div><p className="muted fine">After the server confirms upload, preparation continues while you browse. Keep the local backend running. Your progress is saved.</p>
    </>}
  </main>;
}
