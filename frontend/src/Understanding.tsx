import { useCallback, useEffect, useState } from 'react';
import { Icon } from './Icons';
import { json, paperUrl, pageOf } from './types';
import type { DocumentData, Unit } from './types';

interface Citation {evidence_id: string; quote: string}
interface Statement {category: string; text: string; basis: string; citations: Citation[]}
interface Relationship {subject: string; predicate: string; object: string; explanation: string; basis: string; citations: Citation[]}
interface Report {document_id: string; model: string; created_at: string; statements: Statement[]; relationships: Relationship[];
  coverage: {entries_read: number; batches_read: number; pages_with_text: number[]; document_pages: number};
  rejected_candidates: unknown[]; validation: string}
interface Answer {question: string; status: string; statements: Statement[]; missing_information: string[];
  trace: {tool: string; query: string; evidence_ids: string[]}[]; validation?: string}
interface Generation {job_id: string; kind: string; status: string; stage: string; error: string | null; question: string; result: Answer | Report | null}
interface Connection {provider: string; url: string; model: string; configured: boolean; key_present: boolean; remote: boolean}
interface State {model: Connection; report: Report | null; jobs: Generation[]}
const sections = [['problem','The problem'],['contribution','Contributions'],['method','How it works'],['finding','Findings'],['limitation','Limitations and caveats']];

export function Citations({citations, data, open}: {citations: Citation[]; data: DocumentData; open(unit: Unit): void}) {
  return <div className="claim-citations">{citations.map((cite,index) => {
    const unit = data.units[cite.evidence_id];
    return unit && <button key={index} title={cite.quote} onClick={() => open(unit)}><Icon name="source" size={13}/> p. {pageOf(unit)} <span>{cite.quote.slice(0,85)}{cite.quote.length > 85 ? '…' : ''}</span></button>;
  })}</div>;
}

export function Understanding({data, view, open}: {data: DocumentData; view: 'overview'|'relationships'|'ask'; open(unit: Unit): void}) {
  const [state, setState] = useState<State | null>(null), [error, setError] = useState('');
  const [settings, setSettings] = useState(false), [busy, setBusy] = useState(false);
  const [question, setQuestion] = useState(''), [relationQuery, setRelationQuery] = useState('');
  const refresh = useCallback(async () => {
    try {setState(await json<State>(paperUrl(data.paper.paper_id) + '/understanding'));}
    catch (error) {setError(String(error));}
  }, [data.paper.paper_id]);
  useEffect(() => {void refresh();}, [refresh]);
  const active = state?.jobs.filter(job => ['queued','processing'].includes(job.status)) || [];
  useEffect(() => {
    if (!active.length) return;
    const timer = setInterval(() => void refresh(), 2000);
    return () => clearInterval(timer);
  }, [active.length, refresh]);
  const generate = async (kind: 'analysis'|'question') => {
    setBusy(true); setError('');
    try {
      await json(paperUrl(data.paper.paper_id) + (kind === 'analysis' ? '/understanding' : '/questions'),
        {method:'POST', headers:{'Content-Type':'application/json'}, body: kind === 'question' ? JSON.stringify({question: question.trim()}) : undefined});
      if (kind === 'question') setQuestion('');
      await refresh();
    } catch (error) {setError(String(error));}
    finally {setBusy(false);}
  };
  const report = state?.report, model = state?.model;
  const analysisJob = state?.jobs.find(job => job.kind === 'analysis');
  const generating = active.some(job => job.kind === 'analysis');
  const answerJobs = state?.jobs.filter(job => job.kind === 'question') || [];
  const relations = report?.relationships.filter(r => (r.subject + ' ' + r.predicate + ' ' + r.object + ' ' + r.explanation).toLowerCase().includes(relationQuery.toLowerCase())) || [];
  return <section className="understanding">
    <div className="understanding-heading"><div><div className="eyebrow">PAPER UNDERSTANDING</div><h2>{view === 'overview' ? 'Understand the research.' : view === 'relationships' ? 'Connect the ideas.' : 'Ask across the evidence.'}</h2>
      <p className="muted">{view === 'overview' ? 'An evidence-backed overview of the problem, approach and findings.' : view === 'relationships' ? 'Explore the relationships proposed from this paper, with supporting passages.' : 'Retrieve relevant passages and table context, then synthesize a cited answer.'}</p></div>
      <button className="secondary" onClick={() => setSettings(!settings)}><Icon name="layers" size={16}/>{model?.configured ? 'Model connection' : 'Connect NVIDIA API'}</button></div>
    {error && <div className="error" role="alert">{error}</div>}
    {settings && model && <ModelSettings current={model} changed={() => {void refresh();}}/>}
    {!data.document ? <div className="empty"><h3>This paper needs conversion first</h3><p>Upload the PDF through Add paper to create the text and evidence needed for analysis.</p></div> : <>
      {model?.remote && <p className="model-destination">Generating analysis or answers sends extracted paper excerpts and your question to {new URL(model.url).hostname}. Your original PDF stays in this workspace.</p>}
      {!model?.configured && state && !settings && <div className="setup-callout"><Icon name="layers" size={25}/><div><h3>Connect a model to analyze your papers</h3><p>No generated overview is available yet. Use your NVIDIA API key, another compatible API, or a local Ollama model.</p></div><button className="primary" onClick={() => setSettings(true)}>Set up connection</button></div>}
      {view !== 'ask' && <div className="analysis-actions"><button className="primary" disabled={!model?.configured || busy || generating} onClick={() => void generate('analysis')}>{generating ? <span className="spinner"/> : <Icon name="play" size={16}/>} {generating ? 'Analyzing paper…' : report ? 'Regenerate understanding' : 'Analyze this paper'}</button>
        {report && <a className="secondary" href={paperUrl(data.paper.paper_id) + '/understanding/export'} download><Icon name="export" size={16}/> Export understanding</a>}
        <span className="muted fine">{generating ? analysisJob?.stage : report ? 'Generated by ' + report.model : 'Reads all available extracted text in batches'}</span></div>}
      {analysisJob?.status === 'failed' && <div className="error" role="alert">{analysisJob.error}{report && ' The previous saved analysis remains available.'}</div>}
      {report && <div className="analysis-provenance"><span>{report.coverage.entries_read} evidence entries read</span><span>{report.coverage.pages_with_text.length}/{report.coverage.document_pages} pages contain analyzed text</span><span>{report.rejected_candidates.length} candidates omitted by source checks</span><p>Model-generated interpretation · source references and quotes checked · figures and equations are represented by extracted text and captions only.</p></div>}
      {view === 'overview' && (report ? <div className="overview-grid">{sections.map(([key,title]) => <article className={'overview-section overview-' + key} key={key}><div className="eyebrow">{title}</div>
        {report.statements.filter(s => s.category === key).map((statement,index) => <div className="cited-statement" key={index}><p>{statement.text}</p><span className="interpretation-label">{statement.basis === 'reported' ? 'Authors report' : 'Model inference'}</span><Citations citations={statement.citations} data={data} open={open}/></div>)}
        {!report.statements.some(s => s.category === key) && <p className="muted fine">No supported statement was retained in this category. This does not establish that the paper contains none.</p>}</article>)}</div> : <div className="analysis-empty"><h3>Start with what the paper means.</h3><p>The overview will explain its problem, contributions, methodology, findings and caveats. Every statement will include a source link.</p><p>Read and Evidence already contain the extracted document. Analysis adds interpretation when a model is connected.</p></div>)}
      {view === 'relationships' && <>
        <label className="search relationship-search"><Icon name="search" size={17}/><input aria-label="Search relationships" placeholder="Find a method, concept, dataset or relationship…" value={relationQuery} onChange={e => setRelationQuery(e.target.value)}/></label>
        <div className="relationship-list">{relations.map((relation,index) => <article className="relationship-card" key={index}>
          <div className="relationship-triple"><strong>{relation.subject}</strong><span><span>{relation.predicate}</span><Icon name="arrow" size={20}/></span><strong>{relation.object}</strong></div>
          <p>{relation.explanation}</p><span className="interpretation-label">{relation.basis === 'reported' ? 'Reported relationship' : 'Inferred relationship'}</span><Citations citations={relation.citations} data={data} open={open}/>
        </article>)}</div>
        {!relations.length && <div className="analysis-empty"><h3>{report ? 'No relationships match' : 'Relationships will appear after analysis'}</h3><p>{report ? 'Try another search, or inspect the full extracted paper.' : 'These are generated from the uploaded paper, with separate evidence for the proposed connections.'}</p></div>}
      </>}
      {view === 'ask' && <>
        <form className="question-form" onSubmit={event => {event.preventDefault(); void generate('question');}}><label htmlFor="paper-question">What would you like to understand?</label>
          <textarea id="paper-question" value={question} onChange={event => setQuestion(event.target.value)} maxLength={3000} placeholder="How does the proposed method relate to the improvements reported in the experiments?"/>
          <div><span className="muted fine">Searches this paper only · up to three evidence search rounds</span><button className="primary" disabled={!model?.configured || busy || question.trim().length < 3 || active.some(job => job.kind === 'question')}>Ask this paper <Icon name="arrow" size={16}/></button></div></form>
        <div className="answer-list">{answerJobs.map(job => {
          const result = job.result as Answer | null;
          return <article className="answer-card" key={job.job_id}><h3>{job.question}</h3>
            {['queued','processing'].includes(job.status) && <p role="status"><span className="spinner"/> {job.stage}</p>}
            {job.error && <p className="error" role="alert">{job.error}</p>}
            {result && <><span className="interpretation-label">{result.status === 'not_found' ? 'Insufficient retrieved evidence' : result.status === 'partial' ? 'Partial answer' : 'Model-generated answer'}</span>
              {result.statements.map((statement,index) => <div className="cited-statement" key={index}><p>{statement.text}</p><span className="interpretation-label">{statement.basis === 'reported' ? 'Authors report' : 'Model inference'}</span><Citations citations={statement.citations} data={data} open={open}/></div>)}
              {result.missing_information.length > 0 && <div className="notice"><strong>What remains unclear</strong>{result.missing_information.map((item,index) => <p key={index}>{item}</p>)}</div>}
              <details className="source-details"><summary>Evidence search activity · {result.trace.length} searches</summary>{result.trace.map((step,index) => <p key={index}><strong>{step.query}</strong><br/>{step.evidence_ids.length} evidence entries retrieved</p>)}<p>{result.validation}</p></details>
            </>}
          </article>;
        })}</div>
      </>}
    </>}
  </section>;
}

function ModelSettings({current, changed}: {current: Connection; changed(): void}) {
  const [provider, setProvider] = useState(current.provider), [url, setUrl] = useState(current.url);
  const [model, setModel] = useState(current.model || 'meta/llama-3.3-70b-instruct'), [key, setKey] = useState('');
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  const save = async (test: boolean) => {
    setBusy(true); setMessage('');
    try {
      await json('/api/model', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider,url,model,key,keep_key:!key && current.key_present && provider === current.provider && url === current.url})});
      setKey(''); changed();
      if (test) {await json('/api/model/test',{method:'POST'}); setMessage('Connected. JSON response received; no paper content was sent for this test.');}
      else setMessage('Connection saved for this backend session.');
    } catch (error) {setMessage(String(error));}
    finally {setBusy(false);}
  };
  return <div className="model-settings"><h3>Model connection</h3>
    <label className="field">Provider<select value={provider} onChange={e => {const next=e.target.value; setProvider(next); setKey(''); setUrl(next === 'nvidia' ? 'https://integrate.api.nvidia.com/v1' : next === 'ollama' ? 'http://127.0.0.1:11434' : ''); setModel(next === 'nvidia' ? 'meta/llama-3.3-70b-instruct' : '');}}><option value="nvidia">NVIDIA hosted API</option><option value="ollama">Local Ollama</option><option value="compatible">Compatible hosted/local API</option></select></label>
    <label className="field">API base URL<input value={url} onChange={e => setUrl(e.target.value)} readOnly={provider === 'nvidia'} placeholder="https://your-provider.example/v1"/></label>
    <label className="field">Model ID<input value={model} onChange={e => setModel(e.target.value)} placeholder="Exact model ID from your provider"/></label>
    {provider !== 'ollama' && <label className="field">API key<input type="password" autoComplete="off" value={key} onChange={e => setKey(e.target.value)} placeholder={current.key_present && provider === current.provider && url === current.url ? 'Existing backend key retained' : 'Enter your API key'}/></label>}
    <p className="muted fine">The key is held in backend memory for this session. It is never stored in browser storage or returned by the API. For persistent setup, use backend environment variables.</p>
    {provider === 'nvidia' && <p className="muted fine">Get your key and exact model ID from <a href="https://build.nvidia.com" target="_blank" rel="noreferrer">NVIDIA Build</a>. Free access and rate limits depend on your account and endpoint. The preset is a starting model, not an evaluated accuracy recommendation.</p>}
    <div className="analysis-actions"><button className="primary" disabled={busy || !model.trim() || !url.trim()} onClick={() => void save(true)}>{busy ? 'Connecting…' : 'Save & test connection'}</button><button className="secondary" disabled={busy || !model.trim() || !url.trim()} onClick={() => void save(false)}>Save connection</button></div>
    {message && <p role="status" className="connection-status">{message}</p>}
  </div>;
}

export function PaperText({data, open}: {data: DocumentData; open(unit: Unit): void}) {
  const [query,setQuery] = useState('');
  const units = Object.values(data.units).filter(u => u.kind === 'text' && !['page_header','page_footer'].includes(u.label) && u.text.trim());
  const visible = units.filter(u => u.text.toLowerCase().includes(query.toLowerCase()));
  return <section className="paper-text"><div className="eyebrow">EXTRACTED DOCUMENT</div><h2>Read the paper.</h2><p className="muted">Docling text, without model rewriting. Tables and visual regions are available in Evidence.</p>
    <div className="analysis-actions"><label className="search"><Icon name="search" size={16}/><input aria-label="Search full paper text" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search extracted text…"/></label>{data.exports.includes('fulltext') && <a className="secondary" href={paperUrl(data.paper.paper_id) + '/exports/fulltext'} download>Download full Markdown</a>}</div>
    {visible.map(unit => <article key={unit.evidence_id} className={'text-unit text-' + unit.label}><button className="source-link" onClick={()=>open(unit)}><Icon name="source" size={13}/> Page {pageOf(unit)}</button>{unit.label === 'section_header' || unit.label === 'title' ? <h3>{unit.text}</h3> : <p>{unit.text}</p>}</article>)}
    {!visible.length && <div className="empty">{data.document ? 'No extracted text matches.' : 'Convert this PDF to read its extracted text.'}</div>}
  </section>;
}
