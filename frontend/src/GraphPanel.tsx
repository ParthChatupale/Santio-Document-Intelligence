import { useEffect, useRef, useState } from 'react';
import { Icon } from './Icons';
import { json, paperUrl } from './types';

interface GraphStatus {
  status: string; available: boolean; entities?: number; edges?: number; message?: string;
}

export default function GraphPanel({id}: {id: string}) {
  const [status, setStatus] = useState<GraphStatus | null>(null);
  const [error, setError] = useState(''), [ready, setReady] = useState(false), [attempt, setAttempt] = useState(0);
  const frame = useRef<HTMLIFrameElement>(null);
  const base = paperUrl(id) + '/graph';
  useEffect(() => {
    const controller = new AbortController();
    setStatus(null); setError(''); setReady(false);
    void (async () => {
      try {
        const next = await json<GraphStatus>(base, {signal: controller.signal});
        if (next.available) await json(base + '/view/api/status', {signal: controller.signal});
        if (!controller.signal.aborted) setStatus(next);
      } catch (cause) {
        if (!controller.signal.aborted) setError(String(cause));
      }
    })();
    return () => controller.abort();
  }, [base, attempt]);
  useEffect(() => {
    const message = (event: MessageEvent) => {
      if (event.origin !== location.origin || event.source !== frame.current?.contentWindow) return;
      if (event.data?.type === 'santio-graph-ready') setReady(true);
      if (event.data?.type === 'santio-graph-error') setError('The graph could not be loaded. Retry to reconnect.');
    };
    window.addEventListener('message', message);
    return () => window.removeEventListener('message', message);
  }, []);
  useEffect(() => {
    if (!status?.available || ready || error) return;
    const timeout = setTimeout(() => setError('The graph is taking too long to load. Retry to reconnect.'), 30000);
    return () => clearTimeout(timeout);
  }, [status, ready, error]);
  const retry = () => setAttempt(old => old + 1);
  return <section className="graph-feature" aria-label="Knowledge graph">
    <div className="graph-feature__toolbar"><span><Icon name="graph" size={15}/> Knowledge graph <span className="badge">Experimental</span>
      {status?.available && <small>{status.entities} entities · {status.edges} connections</small>}</span>
      {status?.available && <a href={base + '/view/'} target="_blank" rel="noopener">Open full view ↗</a>}
    </div>
    {error ? <div className="graph-feature__notice" role="alert"><h2>Graph unavailable</h2><p>{error}</p><button className="secondary" onClick={retry}>Retry graph</button></div> :
      status && !status.available ? <div className="graph-feature__notice"><Icon name="graph" size={32}/><h2>{status.status === 'not_prepared' ? 'No graph prepared for this paper' : 'Graph unavailable'}</h2><p>{status.message}</p>
        {status.status !== 'not_prepared' && <button className="secondary" onClick={retry}>Retry graph</button>}</div> :
      <div className="graph-feature__canvas">
        {!ready && <div className="graph-feature__loading" role="status"><span className="spinner"/> Opening this paper’s graph…</div>}
        {status?.available && <iframe key={id + attempt} ref={frame} src={base + '/view/'} title="Paper knowledge graph and graph questions" allowFullScreen
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads" className={ready ? 'is-ready' : ''}/>}
      </div>}
  </section>;
}
