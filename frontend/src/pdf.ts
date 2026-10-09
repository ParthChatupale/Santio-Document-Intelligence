// PDF.js is the existing locally vendored distribution, shared by both frontends.
// Its worker/fonts/cMaps are served locally; no CDN and no eval.
import type { Viewport } from './geometry';
export interface PDFPage {
  view: number[];
  getViewport(options: {scale: number}): Viewport;
  render(options: object): {promise: Promise<void>; cancel(): void};
  streamTextContent(): unknown;
}
export interface PDFDocument {numPages: number; getPage(page: number): Promise<PDFPage>; destroy(): Promise<void>}
export interface TextLayer {render(): Promise<void>; cancel(): void}
interface PDFModule {
  getDocument(options: object): {promise: Promise<PDFDocument>; destroy(): Promise<void>};
  GlobalWorkerOptions: {workerSrc: string};
  TextLayer: new (options: object) => TextLayer;
}
let library: Promise<PDFModule> | undefined;
export function pdfLibrary() {
  // Versioned URLs avoid reusing a cached pre-fix Windows text/plain response.
  const moduleUrl = '/static/vendor/pdf.mjs?v=6.4.299-react';
  library ||= import(/* @vite-ignore */ moduleUrl).then(module => {
    module.GlobalWorkerOptions.workerSrc = '/static/vendor/pdf.worker.mjs?v=6.4.299-react';
    return module as PDFModule;
  });
  return library;
}
export const pdfOptions = (url: string) => ({
  url, cMapUrl: '/static/vendor/cmaps/', cMapPacked: true,
  standardFontDataUrl: '/static/vendor/standard_fonts/', wasmUrl: '/static/vendor/wasm/', isEvalSupported: false,
});
