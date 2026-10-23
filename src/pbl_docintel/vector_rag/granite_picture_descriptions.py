"""Local Granite picture enrichment used by the sandbox converter.

Docling still detects/crops the pictures and extracts their author captions.
Only pictures without usable captions are sent to the local vision model.
It never calls a hosted API or changes extracted author captions.
"""

import gc
from importlib.metadata import version
import json
from pathlib import Path
from time import perf_counter


MODEL = "ibm-granite/granite-vision-3.3-2b"
REVISION = "bf66a8244401a8e26d2ff429aa82df8550a289e5"
PROMPT = (
    "Describe this figure in at most 90 words using only visible evidence. "
    "For a chart, state the axes, legend categories, colors and overall trend. "
    "For a diagram, describe the labeled components and visible arrows. "
    "Do not invent missing labels, numeric values, comparisons or explanations. "
    "If text is unreadable, say so."
)
MAX_NEW_TOKENS = 200
MAX_SECONDS = 120


def describe_pictures(document, output_dir: Path, *, min_area: float = 0.0) -> dict:
    """Reuse nonempty linked captions; generate descriptions only for missing ones."""
    from docling_core.types.doc import TextItem

    if not 0 <= min_area <= 1:
        raise ValueError("min_area must be between 0 and 1.")
    report = {
        "model": MODEL, "revision": REVISION, "device": "cuda:0",
        "quantization": "4-bit NF4 language layers; bfloat16 vision/projector/output layers",
        "prompt": PROMPT, "max_new_tokens": MAX_NEW_TOKENS,
        "generation_time_budget_seconds": MAX_SECONDS,
        "minimum_picture_page_area": min_area,
        "local_files_only": True, "status": "initializing", "items": [],
        "policy": "extracted caption first; Granite only when no nonempty caption resolves",
        "model_loaded": False,
        "ai_descriptions_are_model_generated_and_unverified": True,
        "versions": {},
    }
    report_path = output_dir / "picture_descriptions_report.json"

    def save():
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    def summarize():
        report["captions_reused"] = sum(e["status"] == "caption_reused" for e in report["items"])
        report["generated"] = sum(e["status"] in {"generated", "needs_review"} for e in report["items"])
        report["failed"] = sum(e["status"] == "failed" for e in report["items"])
        report["skipped"] = sum(e["status"] == "skipped" for e in report["items"])
        report["needs_review"] = sum(e["status"] == "needs_review" for e in report["items"])
        save()

    eligible = []
    for picture in document.pictures:
        entry = {"source_ref": picture.self_ref, "status": "pending", "text_source": None,
                 "caption_refs": [], "caption_resolution_errors": []}
        captions = []
        for ref in picture.captions:
            try:
                caption = ref.resolve(document)
                if isinstance(caption, TextItem) and caption.text.strip():
                    captions.append(caption.text.strip())
                    entry["caption_refs"].append(ref.cref)
            except (ValueError, KeyError, IndexError, AttributeError, TypeError, RuntimeError) as exc:
                entry["caption_resolution_errors"].append({"ref": ref.cref, "error": str(exc)})
        if captions:
            entry.update(status="caption_reused", text_source="extracted_caption",
                         text="\n".join(captions))
        else:
            entry["fallback_reason"] = "no_nonempty_caption_detected"
        if picture.prov:
            prov = picture.prov[0]
            entry["page"] = prov.page_no
            page = document.pages.get(prov.page_no)
            if page and page.size.width * page.size.height > 0:
                area = prov.bbox.area() / (page.size.width * page.size.height)
                entry["page_area_fraction"] = round(area, 5)
                if entry["status"] == "pending" and area < min_area:
                    entry.update(status="skipped", reason="below configured page-area threshold")
        report["items"].append(entry)
        if entry["status"] == "pending":
            eligible.append((picture, entry))
    if not eligible:
        report["status"] = "captions_only" if report["items"] and all(
            e["status"] == "caption_reused" for e in report["items"]
        ) else "no_eligible_pictures"
        summarize()
        print(f"Reused {report['captions_reused']} figure captions; Granite was not loaded.", flush=True)
        return report

    print(f"Reused {sum(e['status'] == 'caption_reused' for e in report['items'])} figure captions; "
          f"{len(eligible)} figures need Granite fallback.", flush=True)
    torch = None
    processor = model = inputs = generated = image = None
    save()
    try:
        import torch
        from docling_core.types.doc import DescriptionMetaField, PictureMeta
        from transformers import AutoModelForImageTextToText, AutoProcessor, BitsAndBytesConfig
        report["versions"] = {name: version(name) for name in ["torch", "transformers", "bitsandbytes"]}
        if not torch.cuda.is_available():
            raise RuntimeError("Granite's tested configuration requires CUDA-enabled PyTorch and an NVIDIA GPU.")
        if not torch.cuda.is_bf16_supported():
            raise RuntimeError("The tested Granite configuration requires bfloat16 support.")
        free, total = torch.cuda.mem_get_info()
        report.update(gpu=torch.cuda.get_device_name(0),
                      free_gpu_gib_before=round(free / 1024**3, 3),
                      total_gpu_gib=round(total / 1024**3, 3))
        if free < 3.5 * 1024**3:
            raise RuntimeError("Less than 3.5 GiB GPU memory is free. Close other GPU workloads and retry.")
        print(f"Loading cached {MODEL} on CUDA (4-bit language layers)...", flush=True)
        started = perf_counter()
        processor = AutoProcessor.from_pretrained(MODEL, revision=REVISION, local_files_only=True)
        model = AutoModelForImageTextToText.from_pretrained(
            MODEL, revision=REVISION, local_files_only=True,
            quantization_config=BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True,
                llm_int8_skip_modules=["model.vision_tower", "model.multi_modal_projector", "lm_head"],
            ),
            device_map={"": 0}, dtype=torch.bfloat16, attn_implementation="sdpa",
        ).eval()
        quantized = [name for name, layer in model.named_modules()
                     if layer.__class__.__name__ == "Linear4bit"]
        if not quantized or any("vision_tower" in name or "multi_modal_projector" in name
                                for name in quantized):
            raise RuntimeError("The tested language-only quantization configuration was not applied.")
        if {str(p.device) for p in model.parameters()} != {"cuda:0"}:
            raise RuntimeError("Granite was not loaded entirely on the GPU.")
        report.update(load_seconds=round(perf_counter() - started, 2),
                      quantized_language_layers=len(quantized), quantized_vision_layers=0,
                      model_loaded=True)
        report["status"] = "processing"
        save()
        for index, (picture, entry) in enumerate(eligible, start=1):
            print(f"Describing figure {index}/{len(eligible)}: {picture.self_ref}", flush=True)
            started = perf_counter()
            try:
                image = picture.get_image(document)
                if image is None:
                    raise RuntimeError("Docling did not retain an image crop for this picture.")
                image = image.convert("RGB")
                entry["image_size"] = list(image.size)
                messages = [{"role": "user", "content": [
                    {"type": "image"}, {"type": "text", "text": PROMPT},
                ]}]
                prompt = processor.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
                inputs = processor(text=prompt, images=image, return_tensors="pt").to(
                    "cuda:0", dtype=torch.bfloat16,
                )
                torch.cuda.reset_peak_memory_stats()
                with torch.inference_mode():
                    generated = model.generate(
                        **inputs, max_new_tokens=MAX_NEW_TOKENS, max_time=MAX_SECONDS,
                        do_sample=False, use_cache=True,
                        pad_token_id=processor.tokenizer.pad_token_id,
                    )
                torch.cuda.synchronize()
                token_ids = generated[0, inputs["input_ids"].shape[-1]:]
                text = processor.decode(token_ids, skip_special_tokens=True).strip()
                elapsed = perf_counter() - started
                if not text:
                    raise RuntimeError("The model returned an empty description.")
                capped = token_ids.numel() >= MAX_NEW_TOKENS
                timed = elapsed >= MAX_SECONDS
                entry.update(status="needs_review" if capped or timed else "generated",
                             text_source="ai_description",
                             text=text, generated_tokens=token_ids.numel(),
                             hit_token_cap=capped, reached_time_budget=timed,
                             seconds=round(elapsed, 2),
                             peak_gpu_allocated_gib=round(torch.cuda.max_memory_allocated() / 1024**3, 3))
                if picture.meta is None:
                    picture.meta = PictureMeta()
                picture.meta.description = DescriptionMetaField(text=text, created_by=f"{MODEL}@{REVISION}")
                picture.meta.description.set_custom_field(
                    namespace="santio", name="generation",
                    value={k: entry[k] for k in ["status", "hit_token_cap", "reached_time_budget"]},
                )
            except Exception as exc:
                entry.update(status="failed", error=f"{type(exc).__name__}: {exc}",
                             seconds=round(perf_counter() - started, 2))
            finally:
                inputs = generated = image = token_ids = None
                torch.cuda.empty_cache()
                save()
        report["status"] = "partial" if any(e["status"] in {"failed", "needs_review"}
                                              for e in report["items"]) else "completed"
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        for entry in report["items"]:
            if entry["status"] == "pending":
                entry.update(status="failed", error=report["error"])
    finally:
        processor = model = inputs = generated = image = None
        gc.collect()
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()
        summarize()
    return report
