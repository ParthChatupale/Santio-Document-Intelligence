import { useEffect, useState } from 'react';
import { json, paperUrl } from './types';
import type { QuestionJob, RagState } from './types';
import { active } from './Processing';
export function AskPanel({id, onCitation, onPrepare}: {id: string; onCitation(page: number, refs: string[], quote?: string): void; onPrepare(job: string): void}) {
  const [state, setState] = useState<RagState>({status:'loading'}), [question,setQuestion] = useState('');
  const [job,setJob] = useState<QuestionJob | null>(null), [history,setHistory] = useState<QuestionJob[]>([]);
  const [error,setError] = useState(''), [busy,setBusy] = useState(false);
  useEffect(() => {
    let alive = true;
    setState({status:'loading'}); setQuestion(''); setJob(null); setHistory([]); setError(''); setBusy(false);
    const refresh = () => void json<RagState>(paperUrl(id) + '/rag').then(s => {if (alive) setState(s);}).catch(e => {if (alive) setError(String(e));});
    refresh();
    void json<QuestionJob[]>(paperUrl(id) + '/questions').then(h => {if (alive) {
      const own = h.filter(j => j.paper_id === id);
      setHistory(own);
      // Pending work resumes; saved answers open only when explicitly selected.
      setJob(own.find(j => active(j.status)) || null);
    }}).catch(e => {if (alive) setError(String(e));});
    return () => {alive = false;};
  }, [id]);
  useEffect(() => {
    if (!active(state.status)) return;
    const timer = setInterval(() => {if (!document.hidden) void json<RagState>(paperUrl(id) + '/rag').then(setState).catch(e => setError(String(e)));}, 4000);
    return () => clearInterval(timer);
  }, [id,state.status]);
  useEffect(() => {
    if (!job || !active(job.status)) return;
    const controller = new AbortController();
    const timer = setInterval(() => void json<QuestionJob>('/api/questions/' + job.question_id, {signal:controller.signal}).then(setJob).catch(e => {if (!controller.signal.aborted) setError(String(e));}), 2000);
    return () => {controller.abort(); clearInterval(timer);};
  }, [job?.question_id,job?.status]);
  useEffect(() => {
    if (job && !active(job.status)) setHistory(previous => previous.some(h => h.question_id === job.question_id)
      ? previous.map(h => h.question_id === job.question_id ? job : h)
      : [job,...previous].slice(0,10));
  }, [job]);
  const prepare = async () => {
    setBusy(true); setError('');
    try {const endpoint = state.job_id && ['failed','cancelled'].includes(state.status) ? '/api/imports/' + state.job_id + '/retry' : paperUrl(id) + '/prepare'; const j = await json<{job_id:string}>(endpoint, {method:'POST'}); onPrepare(j.job_id);} catch(e) {setError(String(e));} finally {setBusy(false);}
  };
  const ask = async () => {
    setBusy(true); setError('');
    try {setJob(await json<QuestionJob>(paperUrl(id) + '/questions', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,context_question_id:job?.status === 'completed' ? job.question_id : undefined})}));} catch(e) {setError(String(e));} finally {setBusy(false);}
  };
  const pages = (source: {pages:number[];source_refs:string[];quote?:string}) => source.pages.map(p => <button className="citation" key={p} onClick={() => onCitation(p,source.source_refs,source.quote)}>Page {p} ↗</button>);
  return <div className="ask-panel"><div className="inspector-heading"><h2>Ask this paper</h2></div><div className="ask-scroll">
    <p className="muted">Questions use passages from this paper. Open citations to inspect the original PDF.</p>
    {error && <p role="alert" className="error">{error}</p>}
    {state.status !== 'ready' ? <div className="notice"><p>{state.status === 'loading' ? 'Checking search readiness…' : 'Prepare this paper’s search index before asking questions.'}</p>{state.status !== 'loading' && <button className="primary" disabled={busy} onClick={() => state.job_id && active(state.status) ? onPrepare(state.job_id) : void prepare()}>{state.job_id && active(state.status) ? 'View preparation' : 'Prepare for questions'}</button>}</div> : <form className="ask-form" onSubmit={e => {e.preventDefault(); void ask();}}><label htmlFor="paper-question">What would you like to understand?</label><textarea id="paper-question" value={question} onChange={e => setQuestion(e.target.value)} maxLength={4000} rows={3} placeholder="Give me the gist, or ask about a method or result…"/><button className="primary" disabled={!question.trim() || busy || !!job && active(job.status)}>Ask paper →</button></form>}
    {job && <article className="answer"><h3>{job.question}</h3>{active(job.status) ? <div role="status"><span className="spinner"/> {job.stage}<button className="source-link" onClick={() => void json<QuestionJob>('/api/questions/' + job.question_id + '/cancel',{method:'POST'}).then(setJob).catch(e => setError(String(e)))}>Cancel question</button></div> : job.error ? <p className="error" role="alert">{job.error}</p> : job.result && <>
      <span className="badge">{({'answered':'Answer with citations','partial':'Partial answer','insufficient_evidence':'Not enough retrieved evidence','clarification_needed':'A little more detail needed'} as Record<string,string>)[job.result.answer.status] || job.result.answer.status.replaceAll('_',' ')}</span>
      <p className="muted fine">Model interpretation · inspect the cited passages to check its reasoning.</p>
      {job.result.retrieval_info?.warnings?.map((warning,i) => <p className="notice" role="status" key={i}>{warning}</p>)}
      {job.result.retrieval_info && <details className="retrieved"><summary>How evidence was selected</summary><p>Meaning-based search and text search find candidates from this paper. Overview questions also include its abstract, introduction and concluding sections when available.</p><p>{job.result.retrieval_info.reranking_status === 'applied' ? 'A relevance model ranked the candidate passages before the answer was written.' : 'Passages use the available search ranking.'} Answers still require quotations from the selected passages.</p></details>}
      {job.result.answer.claims.map((claim,i) => <section className="answer-claim" key={i}><p>{claim.text}</p>{claim.evidence.map((e,n) => <div className="answer-evidence" key={n}><blockquote>{e.quote}</blockquote>{pages(e)}</div>)}</section>)}
      {job.result.answer.missing_information && <p className="notice">{job.result.answer.missing_information}</p>}
      <details className="retrieved"><summary>Retrieved passages · {job.result.sources.length}</summary>{job.result.sources.map(s => <section key={s.source_id}><strong>{s.source_id}</strong>{pages(s)}<p>{s.text}</p></section>)}</details>
      <p className="muted fine">Quotes are checked against retrieved text. This does not independently verify the answer’s interpretation.</p>
    </>}</article>}
    {history.some(h => h.question_id !== job?.question_id) && <details className="question-history"><summary>Previous questions</summary>{history.filter(h => h.question_id !== job?.question_id).map(h => <button className="source-link" key={h.question_id} onClick={() => setJob(h)}>{h.question}</button>)}</details>}
  </div></div>;
}
