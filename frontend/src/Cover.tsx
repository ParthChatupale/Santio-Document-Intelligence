import { useEffect, useRef, useState } from 'react';
import { pdfLibrary, pdfOptions } from './pdf';
import { paperUrl } from './types';

// Share a small rendering budget across the shelf, including filter changes.
let activePreviews = 0;
const pendingPreviews = new Set<() => void>();
function queuePreview(render: () => Promise<void>) {
  const start = () => {
    pendingPreviews.delete(start); activePreviews++;
    void render().finally(() => {
      activePreviews--; pendingPreviews.values().next().value?.();
    });
  };
  if (activePreviews < 2) start(); else pendingPreviews.add(start);
  return () => pendingPreviews.delete(start);
}

export function Cover({id}: {id: string}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [status, setStatus] = useState('loading');
  useEffect(() => {
    let disposed = false;
    let task: ReturnType<Awaited<ReturnType<typeof pdfLibrary>>['getDocument']> | undefined;
    let cancel: (() => void) | undefined;
    let dequeue: (() => void) | undefined;
    const render = async () => {
      try {
        const pdf = await pdfLibrary(); if (disposed) return;
        task = pdf.getDocument(pdfOptions(paperUrl(id) + '/pdf'));
        const document = await task.promise; if (disposed) return;
        const page = await document.getPage(1); if (disposed) return;
        const viewport = page.getViewport({scale: 300 / page.getViewport({scale: 1}).width});
        const canvas = ref.current!;
        canvas.width = viewport.width; canvas.height = viewport.height;
        const painting = page.render({canvas, canvasContext: canvas.getContext('2d'), viewport});
        cancel = () => painting.cancel();
        await painting.promise; if (!disposed) setStatus('ready');
      } catch (error) { if (!disposed) {console.warn('PDF cover preview unavailable:', error); setStatus('error');} }
      finally { if (!disposed) await task?.destroy(); }
    };
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        observer.disconnect(); dequeue = queuePreview(render);
      }
    }, {rootMargin: '180px'});
    observer.observe(ref.current!);
    return () => { disposed = true; observer.disconnect(); dequeue?.(); cancel?.(); void task?.destroy(); };
  }, [id]);
  return <div className="cover" data-status={status}><canvas ref={ref} aria-label="Original first page preview"/>{status !== 'ready' && <span>{status === 'error' ? 'Preview unavailable' : 'Loading preview…'}</span>}</div>;
}
