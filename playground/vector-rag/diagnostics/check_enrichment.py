"""Small, offline enrichment probes. Does not alter the converter or its exports.

Uses cached Docling models and selected crops from an existing document, without
reconverting the PDF. Outputs are experimental and are not promoted to RAG input.
"""

import argparse
import json
import os
from pathlib import Path
from time import perf_counter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["picture", "formula"])
    parser.add_argument("document", type=Path)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    import pypdfium2 as pdfium
    import torch
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.pipeline_options import (
        CodeFormulaVlmOptions, PictureDescriptionVlmEngineOptions,
    )
    from docling.datamodel.vlm_engine_options import TransformersVlmEngineOptions
    from docling.models.inference_engines.vlm import VlmEngineInput, create_vlm_engine
    from docling.models.stages.code_formula.code_formula_vlm_model import CodeFormulaVlmModel
    from docling_core.types.doc import DoclingDocument

    # Use the cached model on CPU with a bounded, reproducible generation budget.
    # Float32 is a diagnostic variable; it is not a recommended setting yet.
    torch.set_num_threads(4)
    doc = DoclingDocument.load_from_json(args.document)
    pdf = pdfium.PdfDocument(args.pdf)
    args.output.mkdir(parents=True, exist_ok=False)
    engine_options = TransformersVlmEngineOptions(
        device="cpu", torch_dtype="float32", compile_model=False,
    )
    options = (
        CodeFormulaVlmOptions.from_preset("codeformulav2", engine_options=engine_options)
        if args.kind == "formula" else
        PictureDescriptionVlmEngineOptions.from_preset("smolvlm", engine_options=engine_options)
    )
    started = perf_counter()
    engine = create_vlm_engine(
        options=engine_options, model_spec=options.model_spec,
        accelerator_options=AcceleratorOptions(device="cpu", num_threads=4),
        artifacts_path=None, enable_remote_services=False,
    )
    report = {
        "kind": args.kind, "document": str(args.document), "pdf": str(args.pdf),
        "model": options.model_spec.default_repo_id,
        "device": "cpu", "dtype": "float32", "threads": 4,
        "model_load_seconds": round(perf_counter() - started, 2),
        "max_new_tokens": 256 if args.kind == "formula" else 200,
        "max_generation_seconds": 45, "cases": [],
        "scope": "Selected crops, not a whole-document evaluation.",
    }
    if args.kind == "formula":
        # Compare only crop margin within this probe. Both cases share all else.
        items = [x for x in doc.texts if x.label == "formula"]
        cases = [(items[0], 1.67, .18), (items[-1], 1.67, .18), (items[-1], 1.67, .02)]
    else:
        # Compare saved-export resolution against a higher-resolution PDF crop.
        cases = [(doc.pictures[0], 1., 0.), (doc.pictures[0], 2., 0.)]

    try:
        for index, (item, scale, margin) in enumerate(cases):
            prov = item.prov[0]
            page = pdf[prov.page_no - 1]
            image = page.render(scale=scale).to_pil().convert("RGB")
            bbox = prov.bbox.to_top_left_origin(page_height=doc.pages[prov.page_no].size.height)
            bbox = bbox.expand_by_scale(margin, margin)
            image = image.crop((
                max(0, round(bbox.l * scale)), max(0, round(bbox.t * scale)),
                min(image.width, round(bbox.r * scale)), min(image.height, round(bbox.b * scale)),
            ))
            image.save(args.output / f"crop-{index}.png")
            extra = {"max_time": 45, "skip_special_tokens": args.kind != "formula"}
            if args.kind == "formula":
                extra["skip_special_tokens"] = False
            input_data = VlmEngineInput(
                image=image, prompt="<formula>" if args.kind == "formula" else options.prompt,
                temperature=0., max_new_tokens=report["max_new_tokens"],
                extra_generation_config=extra,
            )
            print(f"Case {index}: {item.self_ref}, page {prov.page_no}, scale={scale}, margin={margin}", flush=True)
            started = perf_counter()
            result = engine.predict_batch([input_data])[0]
            cleaned = result.text
            if args.kind == "formula":
                cleaned = CodeFormulaVlmModel._post_process(None, [cleaned])[0]
            record = {
                "ref": item.self_ref, "page": prov.page_no, "scale": scale, "margin": margin,
                "image_size": list(image.size), "seconds": round(perf_counter() - started, 2),
                "raw_text": result.text, "cleaned_text": cleaned,
                "metadata": result.metadata, "stop_reason": result.stop_reason,
                "original_text": getattr(item, "orig", None),
                "note": "Generation is capped; reaching the cap is not a complete transcription.",
            }
            report["cases"].append(record)
            (args.output / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(record), flush=True)
    finally:
        engine.cleanup()
        pdf.close()


if __name__ == "__main__":
    main()
