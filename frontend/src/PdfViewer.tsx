import { useEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import { pdfLibrary, pdfOptions } from './pdf';
import type { PDFDocument, PDFPage, TextLayer } from './pdf';
import { projectRect } from './geometry';
import type { Viewport } from './geometry';
import type { Unit } from './types';
import { paperUrl } from './types';
import { Icon } from './Icons';

interface Props {
  id: string; page: number; setPage(page: number): void;
  units: Unit[]; selected?: Unit; support: string[];
  onSelect(unit: Unit): void; onCrop(value: string | null): void;
}
export function PdfViewer({id, page, setPage, units, selected, support, onSelect, onCrop}: Props) {
  const [document, setDocument] = useState<PDFDocument | null>(null);
  const [error, setError] = useState('');
  const [zoom, setZoom] = useState(1);
  const [width, setWidth] = useState(500);
  const [overlays, setOverlays] = useState(true);
  const [all, setAll] = useState(false);
  const [painted, setPainted] = useState<{page: PDFPage; viewport: Viewport; number: number; id: string} | null>(null);
  const scroller = useRef<HTMLDivElement>(null), canvas = useRef<HTMLCanvasElement>(null), text = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const container = scroller.current!;
    const observer = new ResizeObserver(() => { if (container.clientWidth > 0) setWidth(container.clientWidth); });
    observer.observe(container); return () => observer.disconnect();
  }, []);
  useEffect(() => {
    let disposed = false;
    let task: ReturnType<Awaited<ReturnType<typeof pdfLibrary>>['getDocument']> | undefined;
    setDocument(null); setPainted(null); setError('');
    void (async () => {
      try {
        const pdf = await pdfLibrary(); if (disposed) return;
        task = pdf.getDocument(pdfOptions(paperUrl(id) + '/pdf'));
        const loaded = await task.promise;
        if (!disposed) setDocument(loaded);
      } catch (error) { if (!disposed) setError(String(error)); }
    })();
    return () => { disposed = true; void task?.destroy(); };
  }, [id]);
  useEffect(() => {
    if (!document) return;
    let disposed = false, painting: ReturnType<PDFPage['render']> | undefined, layer: TextLayer | undefined;
    setPainted(null); onCrop(null); setError('');
    const number = Math.max(1, Math.min(page, document.numPages));
    if (number !== page) setPage(number);
    void (async () => {
      try {
        const pdf = await pdfLibrary(), source = await document.getPage(number);
        if (disposed) return;
        const viewport = source.getViewport({scale: Math.max(.15, (width - 48) / source.getViewport({scale: 1}).width) * zoom});
        const target = canvas.current!, dpr = Math.min(devicePixelRatio || 1, 2);
        target.width = Math.ceil(viewport.width * dpr); target.height = Math.ceil(viewport.height * dpr);
        target.style.width = viewport.width + 'px'; target.style.height = viewport.height + 'px';
        const container = text.current!;
        container.replaceChildren();
        container.style.setProperty('--scale-factor', String(viewport.width / source.getViewport({scale: 1}).width));
        container.style.setProperty('--total-scale-factor', String(viewport.width / source.getViewport({scale: 1}).width));
        container.style.setProperty('--user-unit', '1');
        painting = source.render({canvas: target, canvasContext: target.getContext('2d'), viewport, transform: dpr === 1 ? null : [dpr,0,0,dpr,0,0]});
        await painting.promise; if (disposed) return;
        layer = new pdf.TextLayer({textContentSource: source.streamTextContent(), container, viewport});
        await layer.render(); if (!disposed) setPainted({page: source, viewport, number, id});
      } catch (error) { if (!disposed && !String(error).includes('Rendering cancelled')) setError(String(error)); }
    })();
    return () => { disposed = true; painting?.cancel(); layer?.cancel(); };
  }, [document, page, width, zoom, id, onCrop, setPage]);
  const ready = painted?.number === page && painted?.id === id ? painted : null;
  useEffect(() => {
    if (!ready || !selected) { onCrop(null); return; }
    const location = selected.locations.find(location => location.page_no === page && location.display_rect);
    if (!location?.display_rect) { onCrop(null); return; }
    const box = projectRect(location.display_rect, ready.page.view, ready.viewport);
    const container = scroller.current!;
    container.scrollTo({left: Math.max(0, box.left + box.width / 2 + 24 - container.clientWidth / 2),
      top: Math.max(0, box.top - container.clientHeight * .25), behavior: 'smooth'});
    const source = canvas.current!, sx = source.width / ready.viewport.width, sy = source.height / ready.viewport.height;
    const crop = globalThis.document.createElement('canvas');
    const ratio = Math.min(2, 1000 / Math.max(box.width, box.height));
    crop.width = Math.max(1, Math.round(box.width * ratio)); crop.height = Math.max(1, Math.round(box.height * ratio));
    crop.getContext('2d')!.drawImage(source, box.left * sx, box.top * sy, box.width * sx, box.height * sy, 0, 0, crop.width, crop.height);
    onCrop(crop.toDataURL('image/png'));
  }, [ready, selected, page, onCrop]);
  useEffect(() => { if (input.current) input.current.value = String(page); }, [page]);
  const navigate = (number: number) => { if (Number.isFinite(number)) setPage(Math.max(1, Math.min(document?.numPages || 1, Math.round(number)))); };
  return <section className="source-panel" aria-label="Original PDF">
    <div className="pdf-toolbar">
      <span className="toolbar-title"><Icon name="source" size={16}/> Original PDF</span>
      <div className="page-control"><button title="Previous page" aria-label="Previous page" disabled={page <= 1} onClick={() => navigate(page-1)}>‹</button>
        <input aria-label="Page number" ref={input} type="number" min="1" max={document?.numPages || 1} defaultValue={page} onBlur={event => navigate(Number(event.target.value))} onKeyDown={event => {if (event.key === 'Enter') event.currentTarget.blur();}}/>
        <span>/ {document?.numPages || '…'}</span><button aria-label="Next page" disabled={!document || page >= document.numPages} onClick={() => navigate(page+1)}>›</button></div>
      <select aria-label="PDF zoom" value={zoom} onChange={event => setZoom(Number(event.target.value))}><option value="1">Fit width</option><option value="1.5">150%</option><option value="2">200%</option><option value="3">300%</option></select>
      <button className={overlays ? 'active icon-button' : 'icon-button'} aria-label="Toggle highlights" title="Toggle highlights" aria-pressed={overlays} onClick={() => setOverlays(!overlays)}><Icon name="layers" size={18}/></button>
      <label className="all-regions"><input type="checkbox" checked={all} onChange={event => setAll(event.target.checked)}/> All regions</label>
    </div>
    <div ref={scroller} className="pdf-scroll">
      {error && <p className="error">{error}</p>}
      {!ready && !error && <span className="pdf-loading" role="status">Rendering original page…</span>}
      <div className="pdf-page" style={{width: ready?.viewport.width, height: ready?.viewport.height}}>
        <canvas ref={canvas} aria-label={'Original PDF page ' + page}/>
        <div ref={text} className="textLayer"/>
        {ready && overlays && <div className="region-layer" style={{width: ready.viewport.width, height: ready.viewport.height}}>
          {units.filter(unit => unit.evidence_id === selected?.evidence_id || support.includes(unit.evidence_id) || (all && unit.kind !== 'table_cell')).flatMap(unit => unit.locations.filter(location => location.page_no === page && location.display_rect).map((location,index) => {
            const box = projectRect(location.display_rect!, ready.page.view, ready.viewport);
            const active = unit.evidence_id === selected?.evidence_id;
            return <button key={unit.evidence_id + index} aria-label={unit.label + ': ' + (unit.text || unit.evidence_id)} title={unit.text || unit.label}
              className={'region ' + (active ? 'selected' : support.includes(unit.evidence_id) ? 'support' : unit.kind)}
              style={box as CSSProperties} onClick={() => onSelect(unit)}/>;
          }))}
        </div>}
      </div>
    </div>
    <div className="source-footer"><span><span className="dot"/> Source-linked evidence</span><span>{selected?.locations.find(location => location.page_no === page)?.granularity === 'table' ? 'Table-level location; cell precision unavailable' : 'Select a region to inspect its evidence'}</span></div>
  </section>;
}
