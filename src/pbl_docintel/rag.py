"""Retrieval chunks retain resolvable evidence IDs and uncertainty metadata."""

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .schema import EvidenceIndex, ResultCollection
from .validation import check_collection


def _encoded(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _text_spans(text: str, limit: int):
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + limit // 2, end)
            if boundary >= 0:
                end = boundary + 1
        yield start, end
        start = end


def rag_chunks(index: EvidenceIndex, *, max_text_chars: int = 2000,
               results: ResultCollection | None = None) -> list[dict]:
    """Return plain page_content/metadata dictionaries for any RAG framework.

    Prose is split by character spans. Table cells retain their full structural
    context and may exceed max_text_chars; numbers are never split or inferred.
    """
    if max_text_chars < 128:
        raise ValueError("max_text_chars must be at least 128")
    result_map: dict[str, list[tuple]] = {}
    if results is not None:
        for record, check in zip(results.records, check_collection(results, index), strict=True):
            result_map.setdefault(record.value_evidence.evidence_id, []).append((record, check))
    chunks = []

    def emit(unit, content, start, end, context_ids):
        evidence_ids = list(dict.fromkeys([unit.evidence_id, *context_ids]))
        locations = [{"evidence_id": eid, **loc.model_dump(mode="json")}
                     for eid in evidence_ids for loc in index.units[eid].locations]
        issues = sorted({issue for eid in evidence_ids for issue in index.units[eid].issues})
        attached = result_map.get(unit.evidence_id, [])
        metadata = {
            "document_id": index.document.document_id,
            "source": index.document.source_filename,
            "producer": index.document.producer,
            "kind": unit.kind, "label": unit.label,
            "evidence_ids_json": _encoded(evidence_ids),
            "locations_json": _encoded(locations),
            "issues_json": _encoded(issues),
            "evidence_spans_json": _encoded([{"evidence_id": unit.evidence_id, "start": start, "end": end}]),
            "result_ids_json": _encoded([r.result_id for r, _ in attached]),
            "check_outcomes_json": _encoded([c["outcome"] for _, c in attached]),
            "review_statuses_json": _encoded([r.review.status for r, _ in attached]),
        }
        pages = {loc["page_no"] for loc in locations}
        if pages:
            metadata.update(page_start=min(pages), page_end=max(pages))
        chunk_id = hashlib.sha256(_encoded({"document_id": index.document.document_id,
                                           "unit": unit.evidence_id, "start": start,
                                           "end": end, "content": content}).encode("utf-8")).hexdigest()
        metadata["chunk_id"] = chunk_id
        chunks.append({"page_content": content, "metadata": metadata})

    for unit in index.units.values():
        if unit.kind == "table" and not unit.context.get("cells"):
            context_ids = unit.context.get("captions", []) + unit.context.get("footnotes", [])
            caption_text = "\n".join(index.units[eid].text for eid in context_ids)
            if caption_text or unit.text:
                emit(unit, "Table structure unavailable; inspect the source layout.\n" +
                     caption_text + "\n" + unit.text, 0, len(unit.text), context_ids)
        elif unit.kind == "table_cell":
            if unit.cell.column_header or unit.cell.row_header or unit.cell.row_section or not unit.text.strip():
                continue
            context_ids = []
            lines = []
            for role, label in (("row_headers", "Row"), ("row_labels", "Row candidate"),
                                ("column_headers", "Column"), ("row_sections", "Section"),
                                ("captions", "Caption"), ("footnotes", "Footnote")):
                ids = [eid for eid in unit.context.get(role, []) if eid not in context_ids]
                context_ids.extend(ids)
                if ids:
                    lines.append(f"{label}: " + " / ".join(index.units[eid].text for eid in ids))
            lines.append("Extracted cell: " + unit.text)
            if unit.issues:
                lines.append("Source flags: " + ", ".join(unit.issues))
            emit(unit, "\n".join(lines), 0, len(unit.text), context_ids)
        elif unit.kind == "text" and unit.label not in {"page_header", "page_footer"} and unit.text.strip():
            for start, end in _text_spans(unit.text, max_text_chars):
                emit(unit, unit.text[start:end], start, end, [])
    return chunks


def resolve_evidence(index: EvidenceIndex, chunk: dict) -> list[dict]:
    """Recover source units for a retrieved chunk; reject cross-document mixups."""
    metadata = chunk["metadata"]
    if metadata["document_id"] != index.document.document_id:
        raise ValueError("Chunk belongs to a different conversion")
    return [index.units[eid].model_dump(mode="json")
            for eid in json.loads(metadata["evidence_ids_json"])]


def write_rag_jsonl(chunks: Iterable[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for chunk in chunks:
            stream.write(_encoded(chunk) + "\n")


def to_langchain_documents(chunks: Iterable[dict]):
    """Optional bridge; importing the core library never imports LangChain."""
    try:
        from langchain_core.documents import Document
    except ImportError as error:
        raise ImportError("Install pbl-document-intelligence[langchain] for this bridge") from error
    return [Document(page_content=c["page_content"], metadata=dict(c["metadata"])) for c in chunks]
