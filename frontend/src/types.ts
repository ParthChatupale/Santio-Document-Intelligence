export interface Paper {
  paper_id: string; title: string; source_pdf: string; role: string; status: string;
  processed: boolean; source_available: boolean; original_filename?: string; rag?: RagState;
}
export interface Rect { left: number; top: number; right: number; bottom: number }
export interface Location { page_no: number; granularity: string; display_rect: Rect | null; bbox: unknown }
export interface Unit {
  evidence_id: string; item_ref: string; kind: string; label: string; text: string;
  locations: Location[]; context: Record<string, string[]>; issues: string[];
  cell: {row_start: number; col_start: number; [key: string]: unknown} | null;
}
export interface Ref { evidence_id: string; quote?: string | null }
export interface Result {
  result_id: string; method: {reported: string; normalized: string | null};
  benchmark: {dataset: {reported: string}; subset: string | null; task: string | null; split: string | null; evidence: Ref[]};
  metric: {name: {reported: string}; direction: string; reported_scale: string | null; unit: string | null; definition_evidence: Ref[]};
  value: {raw: string; numeric: number | null; uncertainty?: string | null}; value_evidence: Ref; method_evidence: Ref | null;
  metric_evidence: Ref[]; conditions: {key: string; value: string; basis: string; evidence: Ref[]}[];
  review: {status: string; note: string | null}; notes: string[];
}
export interface Check {result_id: string; outcome: string; errors: string[]; warnings: string[]}
export interface DocumentData {
  paper: Paper; units: Record<string, Unit>; records: Result[]; checks: Check[];
  counts: Record<string, number>; exports: string[]; source_sha256: string; source_status: string;
  document: {document_id: string; pages: Record<string, {width: number; height: number}>} | null;
}
export interface Job {
  job_id: string; filename: string; title: string; status: string; stage: string;
  paper_id: string | null; error: string | null; conversion_status?: string;
  phase?: string; completed_stages?: string[]; size_bytes?: number; done?: number; total?: number;
}
export interface RagState {status: string; job_id?: string; error?: string; chunk_count?: number}
export interface Evidence {source_id: string; quote: string; pages: number[]; source_refs: string[]}
export interface ProviderRetry {
  stage: string; reason: string; retry_number: number; maximum_retries: number; retry_at: string;
}
export interface QuestionJob {
  question_id: string; paper_id: string; question: string; status: string; stage: string; error: string | null;
  retry?: ProviderRetry | null;
  result: {answer: {status: string; claims: {text: string; evidence: Evidence[]}[]; missing_information: string};
    retrieval_info?: {method: string; intent?: string; reranking_status?: string; warnings?: string[]};
    sources: {source_id: string; text: string; pages: number[]; source_refs: string[]}[]; elapsed_seconds: number} | null;
}
export const paperUrl = (id: string) => '/api/papers/' + encodeURIComponent(id);
export async function json<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = Array.isArray(body.detail) ? body.detail.map((item: {msg: string}) => item.msg).join('; ') : body.detail;
    throw new Error(detail || response.statusText);
  }
  return response.json();
}
export function unitTitle(unit: Unit, units: Record<string, Unit>) {
  const caption = unit.context.captions?.map(id => units[id]?.text).filter(Boolean).join(' ');
  return caption || unit.text || (unit.label === 'formula' ? 'Equation · transcription unavailable' : unit.kind === 'picture' ? 'Figure · source region' : 'Table · source region');
}
export const pageOf = (unit?: Unit) => unit?.locations[0]?.page_no || 1;
export function supportingRefs(record: Result): Ref[] {
  return [
    ...(record.method_evidence ? [record.method_evidence] : []), ...record.metric_evidence,
    ...record.benchmark.evidence, ...record.metric.definition_evidence,
    ...record.conditions.flatMap(condition => condition.evidence),
  ].filter((ref, index, all) => all.findIndex(other => other.evidence_id === ref.evidence_id) === index);
}
