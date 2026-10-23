"""Step 2: turn a saved DoclingDocument into inspectable, token-sized chunks.

Uses Docling's HybridChunker and the future embedding model's tokenizer.
Does not load embedding weights, create vectors, or call an answer model.
"""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
from time import perf_counter
from .config import SANDBOX_ROOT
import warnings


TOKENIZER_MODEL = "ibm-granite/granite-embedding-small-english-r2"
TOKENIZER_REVISION = "2ab6fa8ea2d674564defd37171ae19079b864b33"
MODEL_MAX_TOKENS = 8192


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def chunk_document(source: Path, output_dir: Path, *, max_tokens: int = 480,
                   revision: str = TOKENIZER_REVISION, include_ai_descriptions: bool = False,
                   formula_text: str = "original") -> dict:
    from docling.chunking import HybridChunker
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
    from docling_core.types.doc import DoclingDocument, PictureMeta, TextItem
    from transformers import AutoTokenizer
    from transformers.utils.hub import cached_file

    source = source.resolve(strict=True)
    if not source.is_file() or source.suffix.lower() != ".json":
        raise ValueError("Choose a saved Docling document JSON file.")
    if output_dir.exists():
        raise ValueError("Output directory already exists; choose a new directory.")
    if formula_text not in {"original", "document"}:
        raise ValueError("formula_text must be 'original' or 'document'.")
    started = perf_counter()
    document = DoclingDocument.load_from_json(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    # Only this newly loaded, in-memory document is changed. Original JSON stays intact.
    # Captions stay in their native text items. AI descriptions are opt-in and
    # remain distinguishable from author text in each chunk's provenance.
    excluded = {"picture_metadata": [], "formula_candidates": []}
    picture_links = []
    included_ai_refs = set()
    caption_resolution_errors = []
    for picture in document.pictures:
        caption_refs = []
        for ref in picture.captions:
            try:
                caption = ref.resolve(document)
                if isinstance(caption, TextItem) and caption.text.strip():
                    caption_refs.append(ref.cref)
            except (ValueError, KeyError, IndexError, AttributeError, TypeError, RuntimeError) as exc:
                caption_resolution_errors.append({"picture_ref": picture.self_ref,
                                                  "caption_ref": ref.cref, "error": str(exc)})
        description = picture.meta.description if picture.meta else None
        description_data = description.model_dump(mode="json") if description else {}
        generation = description_data.get("santio__generation", {})
        # Only the captionless fallback belongs in this experimental mode.
        # Failed/truncated outputs remain in the sidecar rather than searchable text.
        include_description = bool(
            include_ai_descriptions and not caption_refs and description
            and description.text.strip()
            and generation.get("status", "generated") == "generated"
            and not generation.get("hit_token_cap")
            and not generation.get("reached_time_budget")
        )
        if include_description:
            included_ai_refs.add(picture.self_ref)
        picture_links.append({
            "picture_ref": picture.self_ref,
            "caption_refs": caption_refs,
            "pages": sorted({p.page_no for p in picture.prov}),
            "description_source": "extracted_caption" if caption_refs else (
                "ai_description" if description else "missing"),
            "ai_description_included": include_description,
            "ai_created_by": description.created_by if description else None,
            "ai_description_unverified": bool(description),
        })
        # Older Docling exports may still carry generated descriptions here.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            annotations = picture.annotations
        if picture.meta is not None or annotations:
            excluded["picture_metadata"].append({
                "source_ref": picture.self_ref,
                "metadata": picture.meta.model_dump(mode="json") if picture.meta else None,
                "annotations": [a.model_dump(mode="json") for a in annotations],
                "description_included_in_chunks": include_description,
            })
        picture.meta = PictureMeta(description=description) if include_description else None
        picture.annotations = []

    formulas_restored = 0
    for item in document.texts:
        if item.label.value == "formula" and item.orig and item.orig != item.text:
            excluded["formula_candidates"].append({
                "source_ref": item.self_ref,
                "extracted_original": item.orig,
                "alternate_exported_text": item.text,
                "reason": "empty formula text" if not item.text else "alternate formula text",
                "selected_text": formula_text if item.text else "original (empty document text)",
                "status": "neither version has been validated for mathematical accuracy",
            })
            if formula_text == "original" or not item.text:
                item.text = item.orig
                formulas_restored += 1

    print(f"Loading tokenizer only: {TOKENIZER_MODEL}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_MODEL, revision=revision)
    special_tokens = tokenizer.num_special_tokens_to_add(pair=False)
    if not 1 <= max_tokens <= MODEL_MAX_TOKENS - special_tokens:
        raise ValueError(f"max_tokens must be 1..{MODEL_MAX_TOKENS - special_tokens}.")
    config_path = cached_file(TOKENIZER_MODEL, "tokenizer_config.json",
                              revision=revision, local_files_only=True)
    resolved_revision = Path(config_path).parent.name if config_path else None
    chunker = HybridChunker(
        tokenizer=HuggingFaceTokenizer(tokenizer=tokenizer, max_tokens=max_tokens),
        merge_peers=True,
        repeat_table_header=True,
    )

    print("Creating HybridChunker chunks with heading context...", flush=True)
    records = []
    violations = []
    known_refs = {item.self_ref for item in [*document.texts, *document.tables,
                                            *document.pictures, *document.key_value_items]}
    for index, chunk in enumerate(chunker.chunk(dl_doc=document)):
        contextualized = chunker.contextualize(chunk=chunk)
        # Count exactly what will later enter the embedding model, including specials.
        token_count = len(tokenizer.encode(contextualized, add_special_tokens=True,
                                          truncation=False))
        refs = list(dict.fromkeys(item.self_ref for item in chunk.meta.doc_items))
        linked_pictures = [p for p in picture_links if p["picture_ref"] in refs
                           or set(p["caption_refs"]) & set(refs)]
        has_ai = bool(included_ai_refs & set(refs))
        text_sources = ["extracted_document"] if any(
            item.label.value != "picture" for item in chunk.meta.doc_items
        ) or not has_ai else []
        if has_ai:
            text_sources.append("ai_description")
        pages = sorted({prov.page_no for item in chunk.meta.doc_items for prov in item.prov})
        chunk_id = f"{digest[:16]}-{index:05d}"
        if token_count > MODEL_MAX_TOKENS:
            violations.append({"chunk_id": chunk_id, "reason": "model token limit exceeded",
                               "tokens": token_count})
        if not contextualized.strip() or not refs or any(ref not in known_refs for ref in refs):
            violations.append({"chunk_id": chunk_id, "reason": "empty content or invalid source refs"})
        records.append({
            "chunk_id": chunk_id,
            "text": chunk.text,
            "contextualized_text": contextualized,
            "headings": chunk.meta.headings or [],
            "source_refs": refs,
            "text_sources": text_sources,
            "picture_links": linked_pictures,
            "pages": pages,
            "tokens_with_special_tokens": token_count,
            "source_items": [{
                "ref": item.self_ref, "label": item.label.value,
                "parent_ref": item.parent.cref if item.parent else None,
                "provenance": [prov.model_dump(mode="json") for prov in item.prov],
            } for item in chunk.meta.doc_items],
        })
    if not records:
        violations.append({"reason": "no chunks produced"})

    covered = {ref for chunk in records for ref in chunk["source_refs"]}
    table_refs = {item.self_ref for item in document.tables}
    caption_refs = {ref.cref for item in [*document.tables, *document.pictures]
                    for ref in item.captions}
    empty_tables = [item.self_ref for item in document.tables if not item.data.table_cells]
    review_notes = []
    if empty_tables:
        review_notes.append("Some source tables have no extracted cells; chunking cannot recover their contents.")
    if excluded["formula_candidates"]:
        review_notes.append(f"Formula text policy is '{formula_text}'; neither original extraction nor enriched formulas are accuracy-validated.")
    if excluded["picture_metadata"] and not include_ai_descriptions:
        review_notes.append("Generated picture descriptions are saved separately and excluded from this baseline; use --include-ai-descriptions to opt in.")
    if included_ai_refs:
        review_notes.append("AI figure descriptions are included and attributed, but have not been fact-checked.")
    if table_refs - covered or caption_refs - covered:
        review_notes.append("Some source table/caption references are absent; inspect the coverage lists.")
    # Coverage is reported explicitly: some layers (e.g. running page headers)
    # are intentionally excluded by Docling. Reference coverage is not accuracy.
    report = {
        "source": str(source), "source_sha256": digest,
        "output_directory": str(output_dir.resolve()),
        "status": "validation_failed" if violations else "ready_for_embedding_review",
        "tokenizer_model": TOKENIZER_MODEL, "tokenizer_revision_requested": revision,
        "tokenizer_revision_resolved": resolved_revision,
        "model_max_tokens": MODEL_MAX_TOKENS, "chunk_token_budget": max_tokens,
        "special_tokens_per_chunk": special_tokens,
        "chunks": len(records),
        "chunks_with_headings": sum(bool(c["headings"]) for c in records),
        "largest_encoded_chunk": max((c["tokens_with_special_tokens"] for c in records), default=0),
        "document_pages": len(document.pages),
        "pages_represented": sorted({p for c in records for p in c["pages"]}),
        "tables_represented": len(table_refs & covered), "tables_total": len(table_refs),
        "unrepresented_table_refs": sorted(table_refs - covered),
        "source_tables_without_cells": empty_tables,
        "caption_refs_represented": len(caption_refs & covered),
        "caption_refs_total": len(caption_refs),
        "unrepresented_caption_refs": sorted(caption_refs - covered),
        "picture_metadata_records": len(excluded["picture_metadata"]),
        "picture_metadata_excluded": sum(not p["description_included_in_chunks"]
                                         for p in excluded["picture_metadata"]),
        "formulas_restored_to_original": formulas_restored,
        "formula_text_policy": formula_text,
        "include_ai_descriptions": include_ai_descriptions,
        "included_ai_picture_refs": sorted(included_ai_refs),
        "unrepresented_ai_picture_refs": sorted(included_ai_refs - covered),
        "caption_resolution_errors": caption_resolution_errors,
        "picture_links": picture_links,
        "policy": "author text/tables/captions; AI fallback descriptions opt-in and attributed; formula representation explicitly selected",
        "violations": violations,
        "review_notes": review_notes,
        "elapsed_seconds": round(perf_counter() - started, 2),
        "versions": {name: version(name) for name in ["docling", "docling-core", "transformers"]},
        "embeddings_created": False,
    }
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    with (output_dir / "chunks.jsonl").open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    write_json(output_dir / "excluded_enrichments.json", excluded)
    write_json(output_dir / "chunking_report.json", report)
    preview = ["# HybridChunker output", "",
               "Contextualized text below is the proposed embedding input. No vectors were created.",
               f"Formula text: {formula_text}. Include AI figure descriptions: {include_ai_descriptions}.", ""]
    for record in records:
        preview.extend([f"## {record['chunk_id']}", "",
                        f"Pages: {record['pages']} | Tokens including specials: {record['tokens_with_special_tokens']}",
                        f"Source refs: {', '.join(record['source_refs'])}", "",
                        f"Text sources: {', '.join(record['text_sources'])}",
                        f"Picture links: {', '.join(p['picture_ref'] for p in record['picture_links']) or 'none'}", "",
                        record["contextualized_text"], "", "---", ""])
    (output_dir / "chunks.md").write_text("\n".join(preview), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True), flush=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path, help="Saved Docling document.json")
    parser.add_argument("--max-tokens", type=int, default=480,
                        help="Chunk budget including heading context, before special tokens (default 480)")
    parser.add_argument("--revision", default=TOKENIZER_REVISION,
                        help="HF tokenizer revision (default: pinned tested commit)")
    parser.add_argument("--include-ai-descriptions", action="store_true",
                        help="Include completed captionless AI descriptions, with attribution; default excludes them")
    parser.add_argument("--formula-text", choices=["original", "document"], default="original",
                        help="Use original PDF formula text or Docling's exported formula text (default original)")
    parser.add_argument("--output-dir", type=Path, help="New directory; existing directories are refused")
    args = parser.parse_args()
    if args.output_dir and args.output_dir.exists():
        parser.error("Output directory already exists; choose a new directory.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output_dir or SANDBOX_ROOT / "outputs" / f"chunks-{args.document.parent.name}-{stamp}"
    report = chunk_document(args.document, output, max_tokens=args.max_tokens, revision=args.revision,
                            include_ai_descriptions=args.include_ai_descriptions,
                            formula_text=args.formula_text)
    return 2 if report["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
