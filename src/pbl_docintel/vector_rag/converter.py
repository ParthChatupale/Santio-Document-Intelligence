"""Step 1: convert a PDF with Docling itself, without our existing application.

This stage extracts document content. It does not chunk, embed, build a graph,
or ask an answer model. Review this file before starting the next stage.
"""

import argparse
from datetime import datetime, timezone
import gc
import json
from pathlib import Path
from time import perf_counter
from .config import SANDBOX_ROOT


def convert_pdf(pdf_path: Path, output_dir: Path, *, ocr: bool = False,
                page_range: tuple[int, int] | None = None, min_picture_area: float = 0.0,
                formula_enrichment: bool = True) -> dict:
    # These are the installed package APIs, not functions from our old extractor.
    from docling.datamodel.base_models import ConversionStatus, InputFormat
    from docling.datamodel.pipeline_options import CodeFormulaVlmOptions, PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling_core.types.doc import ImageRefMode

    pdf_path = pdf_path.resolve(strict=True)
    if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
        raise ValueError("Choose an existing PDF file.")
    output_dir = output_dir.resolve()
    # Refuse an existing output directory so a rerun cannot overwrite an export.
    output_dir.mkdir(parents=True, exist_ok=False)

    # OCR is opt-in for scans. Native-text PDFs do not usually need OCR.
    # Docling extracts first. Missing-caption Granite fallbacks run afterward so their
    # models do not compete with Docling's models for the laptop's 6 GB GPU.
    options = PdfPipelineOptions(
        do_ocr=ocr,
        do_table_structure=True,
        generate_picture_images=True,
        images_scale=2.0,
        do_picture_description=False,
        do_formula_enrichment=formula_enrichment,
    )
    # Tighter crops reduce neighbouring-column text entering formula recognition.
    # This improved a failing sample; other formulas still need output review.
    options.code_formula_options = CodeFormulaVlmOptions.from_preset(
        "codeformulav2",
        expansion_factor=0.02,
        stop_on_repetition=True,
    )
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
    )

    print(f"Converting PDF with Docling: {pdf_path}", flush=True)
    started = perf_counter()
    kwargs = {"page_range": page_range} if page_range else {}
    result = converter.convert(source=pdf_path, raises_on_error=False, **kwargs)
    conversion_seconds = round(perf_counter() - started, 2)

    # Release the cached extraction/formula pipelines before loading Granite.
    converter.initialized_pipelines.clear()
    del converter
    gc.collect()
    import torch
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # A partial conversion must remain visibly partial, even if it has content.
    has_content = result.status in {
        ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS
    }
    if has_content:
        document = result.document
        from .granite_picture_descriptions import describe_pictures
        picture_report = describe_pictures(document, output_dir, min_area=min_picture_area)
        # JSON is the complete DoclingDocument, including hierarchy and provenance.
        # Embedded pictures make this export self-contained.
        document.save_as_json(
            output_dir / "document.json", image_mode=ImageRefMode.EMBEDDED,
        )
        # Markdown is a readable companion, with pictures exported beside it.
        document.save_as_markdown(
            output_dir / "document.md", image_mode=ImageRefMode.REFERENCED,
        )

    status = result.status.value
    if has_content and picture_report["status"] in {"partial", "failed"}:
        status = "partial_success"
    report = {
        "source": str(pdf_path),
        "output_directory": str(output_dir),
        "status": status,
        "extraction_status": result.status.value,
        "requested_page_range": list(page_range) if page_range else "all",
        "conversion_seconds": conversion_seconds,
        "total_seconds_including_picture_enrichment_and_export": round(perf_counter() - started, 2),
        "ocr_enabled": ocr,
        "pages": len(result.document.pages) if has_content else 0,
        "text_items": len(result.document.texts) if has_content else 0,
        "tables": len(result.document.tables) if has_content else 0,
        "pictures": len(result.document.pictures) if has_content else 0,
        "errors": [error.model_dump(mode="json") for error in result.errors],
        # These report requested settings, not a guarantee that every item was enriched.
        "picture_description_enabled": True,
        "picture_description_engine": "extracted captions first; local Granite fallback for missing captions",
        "picture_descriptions": picture_report if has_content else {"status": "not_run"},
        "formula_enrichment_enabled": options.do_formula_enrichment,
        "formula_crop_expansion_factor": options.code_formula_options.expansion_factor,
        "formula_stop_on_repetition": options.code_formula_options.stop_on_repetition,
    }
    (output_dir / "conversion_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="PDF to convert afresh with Docling")
    parser.add_argument("--ocr", action="store_true", help="Enable OCR for scanned pages")
    parser.add_argument("--output-dir", type=Path, help="New output directory; must not already exist")
    parser.add_argument("--page-range", type=int, nargs=2, metavar=("FIRST", "LAST"),
                        help="Convert an inclusive page range for a small test")
    parser.add_argument("--min-picture-area", type=float, default=0.0,
                        help="Optionally skip captionless figures below this page-area fraction (default 0: no size skip)")
    parser.add_argument("--no-formulas", action="store_true",
                        help="Skip formula enrichment for an isolated picture-description test")
    args = parser.parse_args()
    if not args.pdf.is_file() or args.pdf.suffix.lower() != ".pdf":
        parser.error("Choose an existing PDF file.")
    if args.page_range and not 1 <= args.page_range[0] <= args.page_range[1]:
        parser.error("Page range must be FIRST LAST with 1 <= FIRST <= LAST.")
    if not 0 <= args.min_picture_area <= 1:
        parser.error("Minimum picture area must be between 0 and 1.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output_dir or SANDBOX_ROOT / "outputs" / f"{args.pdf.stem}-{stamp}"
    report = convert_pdf(args.pdf, output, ocr=args.ocr,
                         page_range=tuple(args.page_range) if args.page_range else None,
                         min_picture_area=args.min_picture_area,
                         formula_enrichment=not args.no_formulas)
    return 0 if report["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
