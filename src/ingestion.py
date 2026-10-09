"""Convert a PDF into a reusable Docling document and readable Markdown."""

import argparse
from collections import Counter
from hashlib import sha256
from importlib.metadata import version
import json
import logging
from pathlib import Path
from time import perf_counter

from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DoclingDocument, ImageRefMode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--ocr", action="store_true", help="Enable OCR for scanned PDFs.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    source = args.pdf.resolve(strict=True)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    options = PdfPipelineOptions()
    options.do_ocr = args.ocr
    options.generate_picture_images = True
    options.heading_hierarchy_options.enabled = True
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    print(f"Converting {source.name} (OCR: {args.ocr})", flush=True)
    started = perf_counter()
    result = converter.convert(source, raises_on_error=False)
    if result.status not in {ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS}:
        raise RuntimeError(f"Conversion status: {result.status.value}; errors: {result.errors}")

    document = result.document
    json_path = output_dir / f"{source.stem}.json"
    markdown_path = output_dir / f"{source.stem}.md"
    figures_dir = output_dir / f"{source.stem}_figures"
    document.save_as_json(json_path, artifacts_dir=figures_dir, image_mode=ImageRefMode.REFERENCED)
    document.save_as_markdown(markdown_path, artifacts_dir=figures_dir, image_mode=ImageRefMode.REFERENCED)

    # Verify that the exported document can be loaded by the downstream layer.
    restored = DoclingDocument.load_from_json(json_path)
    items = [*restored.texts, *restored.tables, *restored.pictures]
    summary = {
        "source": str(source),
        "source_sha256": sha256(source.read_bytes()).hexdigest(),
        "docling_version": version("docling"),
        "status": result.status.value,
        "duration_seconds": round(perf_counter() - started, 2),
        "options": {
            "ocr": options.do_ocr,
            "table_structure": options.do_table_structure,
            "heading_hierarchy": options.heading_hierarchy_options.enabled,
            "picture_images": options.generate_picture_images,
            "formula_enrichment": options.do_formula_enrichment,
        },
        "pages": len(restored.pages),
        "text_items": len(restored.texts),
        "text_labels": dict(Counter(item.label.value for item in restored.texts)),
        "tables": len(restored.tables),
        "pictures": len(restored.pictures),
        "items_with_provenance": sum(bool(item.prov) for item in items),
        "total_content_items": len(items),
        "headings": [
            {"text": item.text, "level": getattr(item, "level", None)}
            for item in restored.texts if item.label.value == "section_header"
        ],
        "table_shapes": [
            {"ref": item.self_ref, "rows": item.data.num_rows,
             "columns": item.data.num_cols, "pages": [prov.page_no for prov in item.prov]}
            for item in restored.tables
        ],
        "errors": [error.model_dump(mode="json") for error in result.errors],
        "outputs": {"json": str(json_path), "markdown": str(markdown_path), "figures": str(figures_dir)},
    }
    summary_path = output_dir / f"{source.stem}.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
        ("status", "duration_seconds", "pages", "text_items", "tables", "pictures", "items_with_provenance")}, indent=2), flush=True)
    print(f"Saved {json_path}\nSaved {markdown_path}\nSaved {summary_path}", flush=True)
    return 0 if result.status == ConversionStatus.SUCCESS else 2


if __name__ == "__main__":
    raise SystemExit(main())
