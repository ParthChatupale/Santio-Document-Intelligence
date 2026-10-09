import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode, CSSProperties } from 'react';
import { Waves } from './Waves';
import { shouldAnimate } from './animation';
import type { MotionPreference } from './animation';
import { Icon } from './Icons';
import { Cover } from './Cover';
import { PdfViewer } from './PdfViewer';
import { json, paperUrl, pageOf, supportingRefs, unitTitle } from './types';
import type { Paper, DocumentData, Job, Unit, Result } from './types';

const categories = ['Results', 'Tables', 'Figures', 'Equations', 'Text'] as const;
type Category = typeof categories[number];
const friendly = (value: string) => value.replaceAll('_', ' ');
const resultLabel = (record: Result) => record.value.numeric === null ? 'Unresolved extraction' : record.value.raw;
const inCategory = (unit: Unit, category: Category) => category === 'Tables' ? unit.kind === 'table' :
  category === 'Figures' ? unit.kind === 'picture' : category === 'Equations' ? unit.label === 'formula' :
  category === 'Text' ? unit.kind === 'text' && unit.label !== 'formula' : false;
function readRoute() {
  const query = new URLSearchParams(location.search);
  return {paper: query.get('paper') || '', page: Math.max(1, Number(query.get('page')) || 1), result: query.get('result') || '', unit: query.get('unit') || ''};
}
function Badge({children, warning = false}: {children: ReactNode; warning?: boolean}) {
  return <span className={'badge ' + (warning ? 'warning' : '')}>{children}</span>;
}
function Dialog({title, children, close}: {title: string; children: ReactNode; close(): void}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); return () => ref.current?.close(); }, []);
  return <dialog ref={ref} className="dialog" onCancel={close} onClick={event => {if (event.target === event.currentTarget) close();}}>
    <div className="dialog-header"><h2>{title}</h2><button className="icon-button" aria-label="Close dialog" onClick={close}><Icon name="close"/></button></div>{children}
  </dialog>;
}
export default function App() {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [route, setRoute] = useState(readRoute);
  const [data, setData] = useState<DocumentData | null>(null);
  const [error, setError] = useState('');
  const [modal, setModal] = useState<'import' | 'exports' | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [motion, setMotion] = useState<MotionPreference>(() => {
    const saved = localStorage.getItem('santio-motion');
    return saved === 'on' || saved === 'off' ? saved : 'system';
  });
  const [reduced, setReduced] = useState(() => matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    const media = matchMedia('(prefers-reduced-motion: reduce)');
    const changed = () => setReduced(media.matches);
    media.addEventListener('change', changed);
    return () => media.removeEventListener('change', changed);
  }, []);
  const animating = shouldAnimate(motion, reduced);
  const refresh = useCallback(() => {void json<Paper[]>('/api/papers').then(setPapers).catch(error => setError(String(error)));}, []);
  const refreshJobs = useCallback(() => {void json<Job[]>('/api/imports').then(setJobs).catch(error => setError(String(error)));}, []);
  useEffect(() => {refresh(); refreshJobs();}, [refresh, refreshJobs]);
  const activeJobs = jobs.filter(job => ['queued', 'processing'].includes(job.status)).length;
  useEffect(() => {
    if (!activeJobs) return;
    const timer = setInterval(() => {
      void json<Job[]>('/api/imports').then(next => {
        if (next.some(job => job.status === 'completed' && jobs.find(old => old.job_id === job.job_id)?.status !== 'completed')) refresh();
        setJobs(next);
      }).catch(error => setError(String(error)));
    }, 2000);
    return () => clearInterval(timer);
  }, [activeJobs, jobs, refresh]);
  useEffect(() => {
    const pop = () => setRoute(readRoute()); window.addEventListener('popstate', pop);
    return () => window.removeEventListener('popstate', pop);
  }, []);
  const navigate = useCallback((paper: string) => {
    const next = {paper, page: 1, result: '', unit: ''};
    history.pushState({}, '', paper ? '?paper=' + encodeURIComponent(paper) : '/');
    setRoute(next); setError('');
  }, []);
  const setPage = useCallback((page: number) => setRoute(old => old.page === page ? old : {...old, page}), []);
  const select = useCallback((unit: string, result = '', page = 1) => setRoute(old => ({...old, unit, result, page})), []);
  useEffect(() => {
    if (!route.paper) { setData(null); return; }
    const controller = new AbortController(); setData(null); setError('');
    void json<DocumentData>(paperUrl(route.paper), {signal: controller.signal}).then(loaded => {
      setData(loaded);
      setRoute(old => {
        if (old.paper !== loaded.paper.paper_id || old.unit) return old;
        const result = loaded.records.find(record => record.result_id === old.result);
        return result ? {...old, unit: result.value_evidence.evidence_id, page: pageOf(loaded.units[result.value_evidence.evidence_id])} : old;
      });
    }).catch(error => {if (!controller.signal.aborted) setError(String(error));});
    return () => controller.abort();
  }, [route.paper]);
  useEffect(() => {
    if (!route.paper) return;
    const query = new URLSearchParams({paper: route.paper, page: String(route.page)});
    if (route.result) query.set('result', route.result);
    if (route.unit && !route.result) query.set('unit', route.unit);
    history.replaceState({}, '', '?' + query);
  }, [route]);
  return <div className={'app-shell ' + (route.paper ? 'reading' : '')}>
    <Waves motion={motion}/>
    <aside className="rail">
      <button className="brand-mark" aria-label="Santio library" onClick={() => navigate('')}><span>S</span><i/></button>
      <button className={!route.paper ? 'rail-button active' : 'rail-button'} title="Library" aria-label="Library" onClick={() => navigate('')}><Icon name="library"/></button>
      <button className="rail-button" title="Upload PDF" aria-label="Upload PDF" onClick={() => setModal('import')}><Icon name="upload"/></button>
      <div className="rail-bottom"><button className="rail-button" title={animating ? 'Pause background motion' : 'Enable background motion'} aria-label={animating ? 'Pause background motion' : 'Enable background motion'} aria-pressed={animating} onClick={() => {
        const next = animating ? 'off' : 'on';
        localStorage.setItem('santio-motion', next); setMotion(next);
      }}><Icon name={animating ? 'pause' : 'play'}/></button><span className="avatar" title="Local workspace">L</span></div>
    </aside>
    <div className="app-main">
      <header className="topbar"><button className="brand-name" onClick={() => navigate('')}>santio<span>RESEARCH WORKSPACE</span></button>
        <div className="topbar-actions"><span className="local-label"><span className="dot"/> Local workspace</span>
          {activeJobs > 0 && <button className="job-indicator" onClick={() => setModal('import')}><span className="spinner"/>{activeJobs} processing</button>}
          <button className="primary small" onClick={() => setModal('import')}><Icon name="upload" size={16}/><span>Add paper</span></button>
        </div>
      </header>
      {error && <div className="error" role="alert">{error}<button onClick={() => {setError(''); refresh();}}>Retry library</button></div>}
      {!route.paper ? <Library papers={papers} open={navigate}/> : data ?
        <Workspace key={data.paper.paper_id} data={data} page={route.page} setPage={setPage} unitId={route.unit} resultId={route.result} select={select} back={() => navigate('')} exports={() => setModal('exports')}/> :
        !error && <div className="loading-screen" role="status"><span className="spinner"/> Opening source and evidence…</div>}
    </div>
    {modal === 'import' && <ImportDialog jobs={jobs} update={refreshJobs} done={() => {refresh(); refreshJobs();}} open={id => {setModal(null); navigate(id);}} close={() => setModal(null)}/>}
    {modal === 'exports' && data && <Dialog title="Export this paper" close={() => setModal(null)}>
      <p className="muted">Evidence and provenance from this document. Result annotations retain their review status.</p>
      <div className="export-list">{data.exports.map(kind => <a key={kind} href={paperUrl(data.paper.paper_id) + '/exports/' + kind} download><Icon name="export"/><span>{({rag:'RAG chunks · JSONL',evidence:'Evidence index · JSON',docling:'Docling document · JSON',results:'Result annotations · JSON',csv:'Result annotations · CSV',markdown:'Result annotations · Markdown',checks:'Attribution findings · JSON'} as Record<string,string>)[kind]}</span><Icon name="arrow" size={16}/></a>)}</div>
      <p className="muted fine">RAG export provides chunks for your Python/retrieval system. It does not generate answers.</p>
    </Dialog>}
  </div>;
}
function Library({papers, open}: {papers: Paper[]; open(id: string): void}) {
  const [query, setQuery] = useState(''), [filter, setFilter] = useState('all');
  const visible = papers.filter(paper => (paper.title + ' ' + paper.paper_id).toLowerCase().includes(query.toLowerCase()) && (filter === 'all' || (filter === 'indexed' ? paper.processed : !paper.processed)));
  return <main className="library">
    <section className="welcome"><div className="eyebrow">FROM PAPERS TO UNDERSTANDING</div><h1>Read deeper.<br/><em>Keep the evidence.</em></h1>
      <p>A quieter place to explore research. Follow tables, figures, and<br className="desktop-break"/> results back to the exact page they came from.</p>
      <div className="welcome-meta"><span><strong>{papers.length}</strong> papers in your library</span><span><strong>{papers.filter(p => p.processed).length}</strong> indexed documents</span><span><Icon name="layers" size={15}/> Provenance included</span></div>
      <span className="hero-art" aria-hidden="true"><i/><i/><i/></span>
    </section>
    <section className="library-content">
      <div className="section-heading"><div><div className="eyebrow">YOUR COLLECTION</div><h2>Paper library <span>{papers.length}</span></h2></div>
        <label className="search"><Icon name="search" size={18}/><input aria-label="Search papers" placeholder="Search your papers…" value={query} onChange={event => setQuery(event.target.value)}/></label></div>
      <div className="library-filters">{[['all','All papers'],['indexed','Indexed'],['source','Source only']].map(([value,label]) => <button key={value} className={filter === value ? 'active' : ''} onClick={() => setFilter(value)}>{label}</button>)}</div>
      <div className="paper-grid">{visible.map(paper => <button className="paper-card" key={paper.paper_id} onClick={() => open(paper.paper_id)} disabled={!paper.source_available}>
        <div className="cover-stage"><Cover id={paper.paper_id}/><span className="cover-open"><Icon name="arrow"/></span></div>
        <div className="paper-card-body"><Badge warning={!paper.processed}>{paper.processed ? paper.status === 'partial_success' ? 'Partially indexed' : 'Indexed' : 'Source only'}</Badge>
          <h3>{paper.title}</h3><div className="paper-card-footer"><span>{paper.original_filename || paper.paper_id}</span><Icon name="arrow" size={16}/></div></div>
      </button>)}</div>
      {!visible.length && <div className="empty"><Icon name="library" size={30}/><h3>{papers.length ? 'No papers match this search' : 'Your library starts here'}</h3><p>{papers.length ? 'Try a different title or filter.' : 'Use Add paper to upload your first PDF.'}</p></div>}
      <div className="library-note"><Icon name="source" size={17}/><span>Original documents stay at the center. Machine detections and curated annotations remain distinguishable.</span></div>
    </section>
  </main>;
}
function ImportDialog({jobs, update, done, open, close}: {jobs: Job[]; update(): void; done(): void; open(id: string): void; close(): void}) {
  const [file, setFile] = useState<File | null>(null), [title, setTitle] = useState(''), [ocr, setOcr] = useState(false);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const choose = (next?: File) => {if (next) {setFile(next); setTitle(next.name.replace(/\.pdf$/i, '')); setError('');}};
  const upload = async () => {
    if (!file) return;
    if (file.size > 100 * 1024 * 1024) {setError('Maximum file size is 100 MB.'); return;}
    setBusy(true); setError('');
    try {
      const query = new URLSearchParams({filename: file.name, title, ocr: String(ocr)});
      await json<Job>('/api/imports?' + query, {method:'POST', headers:{'Content-Type':'application/pdf'}, body:file});
      setFile(null); setTitle(''); done();
    } catch (error) {setError(String(error));}
    finally {setBusy(false);}
  };
  return <Dialog title="Add a research paper" close={close}>
    <p className="muted">Upload a PDF. Docling extracts its structure, then Santio creates source-linked evidence and RAG chunks.</p>
    <label className="drop-zone" onDragOver={event => event.preventDefault()} onDrop={event => {event.preventDefault(); choose(event.dataTransfer.files[0]);}}>
      <Icon name="upload" size={30}/><strong>{file?.name || 'Drop your PDF here'}</strong><span>or choose a file · up to 100 MB</span><input aria-label="Choose PDF" type="file" accept=".pdf,application/pdf" disabled={busy} onChange={event => choose(event.target.files?.[0])}/>
    </label>
    <label className="field">Paper title<input value={title} onChange={event => setTitle(event.target.value)} placeholder="Use the filename or enter a title" maxLength={500}/></label>
    <label className="checkbox"><input type="checkbox" checked={ocr} onChange={event => setOcr(event.target.checked)}/> Enable OCR for scanned pages</label>
    {error && <p className="error" role="alert">{error}</p>}
    <button className="primary import-button" disabled={!file || busy} onClick={() => void upload()}>{busy ? <span className="spinner"/> : <Icon name="upload" size={18}/>} {busy ? 'Uploading PDF…' : 'Upload & process'}</button>
    <p className="muted fine">Processing continues when this window closes. First use may download Docling models. Detected equations and figures are not automatically interpreted.</p>
    {jobs.length > 0 && <div className="job-list"><h3>Imports</h3>{jobs.slice(0,8).map(job => <div className="job-row" key={job.job_id}>
      <div><strong>{job.title}</strong><span>{job.stage}{job.conversion_status === 'partial_success' ? ' · partial conversion' : ''}</span>{job.error && <details><summary>Processing error · upload again to retry</summary><pre>{job.error}</pre></details>}</div>
      {job.status === 'completed' && job.paper_id ? <button onClick={() => open(job.paper_id!)}>Open <Icon name="arrow" size={15}/></button> :
        ['queued','processing'].includes(job.status) ? <button onClick={() => void json('/api/imports/' + job.job_id + '/cancel', {method:'POST'}).then(update).catch(error => setError(String(error)))}>Cancel</button> : <Badge warning>{job.status}</Badge>}
    </div>)}</div>}
  </Dialog>;
}
function Workspace({data, page, setPage, unitId, resultId, select, back, exports}: {
  data: DocumentData; page: number; setPage(page: number): void; unitId: string; resultId: string;
  select(unit: string, result?: string, page?: number): void; back(): void; exports(): void;
}) {
  const initialUnit = data.units[unitId];
  const unitCategory = (unit: Unit): Category => unit.label === 'formula' ? 'Equations' : unit.kind === 'picture' ? 'Figures' : unit.kind.startsWith('table') ? 'Tables' : 'Text';
  const [category, setCategory] = useState<Category>(resultId ? 'Results' : initialUnit ? unitCategory(initialUnit) : data.records.length ? 'Results' : data.counts.table ? 'Tables' : data.counts.picture ? 'Figures' : 'Text');
  const [task, setTask] = useState<'inspect'|'review'|'compare'>('inspect');
  const [tab, setTab] = useState('source'), [query, setQuery] = useState('');
  const [crop, setCrop] = useState<string | null>(null);
  const [panelWidth, setPanelWidth] = useState(400);
  const units = useMemo(() => Object.values(data.units), [data]);
  const selected = data.units[unitId], record = data.records.find(record => record.result_id === resultId);
  const refs = useMemo(() => record ? supportingRefs(record).map(ref => ref.evidence_id) : [], [record]);
  const allChecks = data.checks.filter(check => check.outcome !== 'evidence_checks_passed');
  const records = data.records.filter(record => (task !== 'review' || allChecks.some(check => check.result_id === record.result_id)) &&
    (record.method.reported + record.benchmark.dataset.reported + record.metric.name.reported).toLowerCase().includes(query.toLowerCase()));
  const filteredUnits = units.filter(unit => inCategory(unit, category) && unitTitle(unit, data.units).toLowerCase().includes(query.toLowerCase()));
  const chooseRecord = (record: Result) => {select(record.value_evidence.evidence_id, record.result_id, pageOf(data.units[record.value_evidence.evidence_id])); setTab('source');};
  const chooseUnit = (unit: Unit) => {setCategory(unitCategory(unit)); select(unit.evidence_id, '', pageOf(unit)); setTab('source');};
  const focusUnit = (unit: Unit) => {select(unit.evidence_id, resultId, pageOf(unit)); setTab('source');};
  const resize = (event: React.PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    const start = event.clientX, initial = panelWidth;
    const move = (next: PointerEvent) => setPanelWidth(Math.min(560, Math.max(320, initial + start - next.clientX)));
    const end = () => {window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', end);};
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', end, {once:true});
  };
  return <main className="workspace">
    <header className="document-header"><button className="icon-button" aria-label="Back to library" onClick={back}><Icon name="back"/></button>
      <div className="document-title"><div className="eyebrow">{data.paper.paper_id}</div><h1>{data.paper.title}</h1></div>
      <button className="secondary export-button" aria-label="Export" disabled={!data.exports.length} onClick={exports}><Icon name="export" size={17}/><span>Export</span></button></header>
    <div className="workspace-taskbar"><div className="task-tabs">{[['inspect','Explore','source'],['review','Review','review'],['compare','Compare','compare']].map(([value,label,icon]) => <button key={value} className={task === value ? 'active' : ''} onClick={() => {
      setTask(value as typeof task); if (value !== 'inspect') setCategory('Results'); setQuery('');
      if (value === 'review') {const first = data.records.find(record => allChecks.some(check => check.result_id === record.result_id)); if (first) chooseRecord(first); else select('', '', page); setTab('evidence');}
    }}><Icon name={icon} size={16}/>{label}{value === 'review' && allChecks.length > 0 && <span>{allChecks.length}</span>}</button>)}</div>
      <span className="task-note">{task === 'review' ? 'Read-only findings · saved reviews pending' : task === 'compare' ? 'Provisional results · compatibility not assessed' : data.document ? 'Docling detections + source provenance' : 'Source only · no extracted evidence'}</span></div>
    {task === 'compare' ? <div className="comparison">
      <div className="eyebrow">REPORTED RESULTS</div><h2>Context before conclusions.</h2><p className="muted">These are existing curated annotations, not an automatically generated or validated leaderboard. Open a value to inspect its source and conditions.</p>
      <div className="table-scroll"><table><thead><tr><th>Method</th><th>Dataset</th><th>Metric</th><th>Extracted value</th><th>Review</th><th>Conditions</th></tr></thead><tbody>{data.records.map(record => <tr key={record.result_id}><td>{record.method.reported}</td><td>{record.benchmark.dataset.reported}</td><td>{record.metric.name.reported}</td><td><button onClick={() => {setTask('inspect'); chooseRecord(record);}}>{resultLabel(record)} ↗</button></td><td><Badge warning={record.review.status === 'needs_review'}>{friendly(record.review.status)}</Badge></td><td>{record.conditions.map(c => c.value).join('; ') || 'Not specified'}</td></tr>)}</tbody></table></div>
      {!data.records.length && <div className="empty">No result annotations for this document. Its detected regions are available in Explore.</div>}
    </div> : <>
      <div className="mobile-tabs"><button className={tab === 'source' ? 'active' : ''} onClick={() => setTab('source')}>Original source</button><button className={tab === 'evidence' ? 'active' : ''} onClick={() => setTab('evidence')}>Evidence{record ? ' · ' + (record.value.numeric === null ? 'issue' : record.value.raw) : ''}</button></div>
      <div className={'workbench tab-' + tab} style={{'--inspector-width': panelWidth + 'px'} as CSSProperties}>
        <PdfViewer id={data.paper.paper_id} page={page} setPage={setPage} units={units} selected={selected} support={refs} onSelect={chooseUnit} onCrop={setCrop}/>
        <div className="resize-handle" role="separator" aria-label="Resize evidence panel" aria-orientation="vertical" tabIndex={0} onPointerDown={resize} onKeyDown={event => {if (event.key === 'ArrowLeft') setPanelWidth(Math.min(560,panelWidth+20)); if (event.key === 'ArrowRight') setPanelWidth(Math.max(320,panelWidth-20));}}/>
        <aside className="evidence-panel" aria-label="Evidence inspector">
          <div className="inspector-heading"><Icon name="layers" size={18}/><h2>Evidence explorer</h2><Badge>{data.document ? 'Indexed' : 'Source only'}</Badge></div>
          <div className="category-tabs" role="tablist" aria-label="Evidence categories">{categories.map(value => <button key={value} role="tab" aria-selected={category === value} className={category === value ? 'active' : ''} onClick={() => {setCategory(value); setQuery(''); select('', '', page);}}>
            {value}<span>{value === 'Results' ? data.records.length : units.filter(unit => inCategory(unit,value)).length}</span></button>)}</div>
          <div className="evidence-scroll">
            {task === 'review' && <div className="notice">Attribution findings require review. These checks do not verify scientific correctness; reviewer decisions are not yet saved in this app.</div>}
            <label className="search inspector-search"><Icon name="search" size={16}/><input aria-label="Search evidence" placeholder={'Find ' + category.toLowerCase() + '…'} value={query} onChange={event => setQuery(event.target.value)}/></label>
            <select className="evidence-picker" aria-label="Select evidence" value={category === 'Results' ? record?.result_id || '' : filteredUnits.some(unit => unit.evidence_id === unitId) ? unitId : ''} onChange={event => {
              if (category === 'Results') {const found = records.find(record => record.result_id === event.target.value); if (found) chooseRecord(found);}
              else {const found = data.units[event.target.value]; if (found) chooseUnit(found);}
            }}><option value="">Choose {category.toLowerCase()} ({category === 'Results' ? records.length : filteredUnits.length})</option>
              {category === 'Results' ? records.map(record => <option key={record.result_id} value={record.result_id}>{record.method.reported} · {record.benchmark.dataset.reported} · {record.metric.name.reported} · {resultLabel(record)}</option>) :
                filteredUnits.map(unit => <option key={unit.evidence_id} value={unit.evidence_id}>p. {pageOf(unit)} · {unitTitle(unit,data.units).slice(0,100)}</option>)}</select>
            {(category === 'Results' ? records.length : filteredUnits.length) === 0 && <div className="empty compact"><h3>No {category.toLowerCase()} {query ? 'match this search' : 'available'}</h3><p>{category === 'Results' ? 'Result interpretation is separate from Docling region detection. No annotations have been added here.' : !data.document ? 'This PDF has not been converted yet.' : 'Docling did not produce this kind of region.'}</p></div>}
            {record && category === 'Results' ? <ResultInspector record={record} data={data} focus={focusUnit}/> : selected ? <UnitInspector unit={selected} data={data} crop={crop} choose={chooseUnit}/> :
              (category === 'Results' ? records.length : filteredUnits.length) > 0 ?
              <div className="empty compact"><Icon name="source" size={30}/><h3>Follow an evidence trail</h3><p>Choose a result or detected region above. Its location and supporting context will appear here.</p></div> : null}
            <details className="evidence-list"><summary>Browse {category.toLowerCase()} · {category === 'Results' ? records.length : filteredUnits.length}</summary>
              <div>{category === 'Results' ? records.map(record => <button key={record.result_id} className={resultId === record.result_id ? 'selected' : ''} onClick={() => chooseRecord(record)}><strong>{record.metric.name.reported}<span>{resultLabel(record)}</span></strong><small>{record.method.reported} · {record.benchmark.dataset.reported}</small></button>) :
                filteredUnits.slice(0,200).map(unit => <button key={unit.evidence_id} className={unitId === unit.evidence_id ? 'selected' : ''} onClick={() => chooseUnit(unit)}><small>PAGE {pageOf(unit)} · {friendly(unit.label)}</small><span>{unitTitle(unit,data.units).slice(0,150)}</span></button>)}</div>
              {filteredUnits.length > 200 && <p className="muted fine">Showing the first 200 regions. Search or use the picker to reach all regions.</p>}</details>
            <details className="source-details"><summary>Document provenance</summary><p>{data.source_status}</p><dl><dt>Source</dt><dd>{data.paper.original_filename || data.paper.source_pdf}</dd><dt>SHA-256</dt><dd>{data.source_sha256}</dd><dt>Conversion ID</dt><dd>{data.document?.document_id || 'Not converted'}</dd></dl></details>
          </div>
        </aside>
      </div>
    </>}
  </main>;
}
function ResultInspector({record, data, focus}: {record: Result; data: DocumentData; focus(unit: Unit): void}) {
  const check = data.checks.find(check => check.result_id === record.result_id);
  const value = data.units[record.value_evidence.evidence_id];
  const issues = [...(check?.errors || []), ...(check?.warnings || [])];
  const unresolved = record.value.numeric === null;
  return <article className="result-inspector">
    <div className="result-heading"><span className="eyebrow">{unresolved ? 'EXTRACTION ISSUE' : 'REPORTED VALUE'}</span><Badge warning={unresolved || !!issues.length}>{unresolved ? 'Mapping unresolved' : issues.length ? 'Needs inspection' : 'Attribution checks passed'}</Badge></div>
    {unresolved ? <div className="extraction-issue"><h3>No single score recovered</h3>
      <p>{record.value.uncertainty || 'This extracted text has not been resolved into a single numeric result.'}</p>
      <div className="raw-extraction"><span>Raw text extracted by Docling</span><code>{record.value.raw}</code></div>
      <p className="fine">Metric context: {record.metric.name.reported}. Inspect the original table before assigning numbers to metrics.</p>
      {record.notes.length > 0 && <details><summary>Source inspection notes · manually annotated</summary>{record.notes.map((note,index) => <p key={index}>{note}</p>)}</details>}
    </div> : <div className="result-value">{record.value.raw}<span>{record.metric.name.reported}</span></div>}
    <button className="source-link" onClick={() => focus(value)}><Icon name="source" size={15}/> View original · page {pageOf(value)}<Icon name="arrow" size={15}/></button>
    <dl className="result-fields"><dt>Method</dt><dd>{record.method.reported}{record.method.normalized && record.method.normalized !== record.method.reported && <small>Interpreted as {record.method.normalized}</small>}</dd>
      <dt>Dataset</dt><dd>{record.benchmark.dataset.reported}</dd><dt>Direction</dt><dd>{record.metric.direction === 'lower' ? 'Lower is better' : record.metric.direction === 'higher' ? 'Higher is better' : 'Not specified'}</dd>
      <dt>Scale</dt><dd>{record.metric.reported_scale || 'As reported'}</dd><dt>Human review</dt><dd><Badge warning={record.review.status === 'needs_review'}>{friendly(record.review.status)}</Badge></dd>
    </dl>
    <h3>Experiment context</h3><div className="context-box">{record.conditions.length ? record.conditions.map((condition,index) => <p key={index}><strong>{friendly(condition.key)}</strong>{condition.value}<small>{condition.basis}</small></p>) : <p>Conditions not annotated.</p>}
      <p><strong>Task / split</strong>{record.benchmark.task || 'Not annotated'} / {record.benchmark.split || 'Not annotated'}</p></div>
    {issues.length > 0 && <div className="notice"><strong>Keep this ambiguity visible</strong>{issues.map(issue => <p key={issue}>{friendly(issue)}</p>)}{record.value.numeric === null && <p>The raw value is preserved; no single numeric value has been assigned.</p>}</div>}
    <h3>Supporting evidence</h3><div className="support-list">{supportingRefs(record).map(ref => {
      const unit = data.units[ref.evidence_id];
      return unit && <button key={ref.evidence_id} onClick={() => focus(unit)}><span>PAGE {pageOf(unit)} · {friendly(unit.label)}</span><p>{ref.quote || unit.text || unitTitle(unit,data.units)}</p><Icon name="arrow" size={14}/></button>;
    })}</div>
    <details className="source-details"><summary>Annotation notes & technical details</summary><p>{record.review.note}</p>{record.notes.map((note,index) => <p key={index}>{note}</p>)}<pre>{JSON.stringify(record,null,2)}</pre></details>
  </article>;
}
function UnitInspector({unit, data, crop, choose}: {unit: Unit; data: DocumentData; crop: string | null; choose(unit: Unit): void}) {
  const cells = unit.context.cells?.map(id => data.units[id]).filter(Boolean) || [];
  const context = [...new Set(Object.entries(unit.context).filter(([key]) => key !== 'cells').flatMap(([,ids]) => ids))].map(id => data.units[id]).filter(Boolean);
  const table = unit.kind === 'table_cell' ? data.units[unit.evidence_id.split('::')[0]] : null;
  return <article className="unit-inspector"><div className="result-heading"><span className="eyebrow">{friendly(unit.label)}</span><Badge>Page {pageOf(unit)}</Badge></div><h3>{unitTitle(unit,data.units)}</h3>
    {crop && ['picture','table','table_cell'].includes(unit.kind) || crop && unit.label === 'formula' ? <img className="evidence-crop" src={crop!} alt="Crop from the original PDF at the selected evidence location"/> : null}
    {unit.text && <p className="extracted-text">{unit.text}</p>}
    {unit.label === 'formula' && !unit.text && <div className="notice">Equation region detected. A transcription is unavailable; inspect the original source crop.</div>}
    {unit.kind === 'picture' && <p className="muted fine">This is a detected picture region. Its contents have not been semantically interpreted.</p>}
    {unit.issues.map(issue => <p className="notice" key={issue}>{friendly(issue)}</p>)}
    {table && <button className="source-link" onClick={() => choose(table)}><Icon name="back" size={14}/> Return to parent table</button>}
    {context.length > 0 && <><h3>Extracted context</h3><div className="support-list">{context.map(item => <button key={item.evidence_id} onClick={() => choose(item)}><span>PAGE {pageOf(item)} · {friendly(item.label)}</span><p>{item.text || unitTitle(item,data.units)}</p></button>)}</div></>}
    {cells.length > 0 && <details className="cell-list"><summary>Extracted table cells · {cells.length}</summary>{cells.map(cell => <button key={cell.evidence_id} onClick={() => choose(cell)}>{cell.text || 'Empty cell'}<Icon name="arrow" size={13}/></button>)}</details>}
    <details className="source-details"><summary>Evidence location & extracted structure</summary><p>Coordinates describe positions, not confidence scores. Location granularity is preserved.</p><pre>{JSON.stringify(unit,null,2)}</pre></details>
  </article>;
}
