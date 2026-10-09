"""Isolated Docling conversion process for a single uploaded PDF."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--ocr", action="store_true")
    args = parser.parse_args()
    # The core SDK and HTTP service never import the model runtime.
    from docling.datamodel.base_models import ConversionStatus, InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling_core.types.doc import ImageRefMode
    from .. import DoclingAdapter, index_document, write_rag_jsonl, rag_chunks

    args.output.mkdir(parents=True, exist_ok=True)
    print("SANTIO_STAGE:Loading Docling models", flush=True)
    options = PdfPipelineOptions()
    options.do_ocr = args.ocr
    options.generate_picture_images = True
    options.heading_hierarchy_options.enabled = True
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    print("SANTIO_STAGE:Converting PDF with Docling", flush=True)
    result = converter.convert(args.source, raises_on_error=False)
    if result.status not in {ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS}:
        raise RuntimeError(f"Docling conversion failed: {result.status.value}; {result.errors}")
    print("SANTIO_STAGE:Saving document and indexing evidence", flush=True)
    document = args.output / "document.json"
    result.document.save_as_json(document, artifacts_dir=args.output / "figures", image_mode=ImageRefMode.REFERENCED)
    result.document.save_as_markdown(args.output / "document.md", artifacts_dir=args.output / "figures", image_mode=ImageRefMode.REFERENCED)
    index = index_document(document, DoclingAdapter(args.source))
    (args.output / "evidence.index.json").write_text(index.model_dump_json(indent=2), encoding="utf-8")
    write_rag_jsonl(rag_chunks(index), args.output / "rag.jsonl")
    (args.output / "receipt.json").write_text(json.dumps({
        "status": result.status.value, "pages": len(result.document.pages),
        "errors": [error.model_dump(mode="json") for error in result.errors],
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
