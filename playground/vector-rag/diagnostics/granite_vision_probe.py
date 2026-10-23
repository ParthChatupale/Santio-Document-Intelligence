"""Run one cached Granite Vision image through 4-bit CUDA inference.

An isolated model probe, not a replacement for Docling's picture stage. It leaves
the converter and saved documents unchanged. No hosted inference API is used.
"""

import argparse
import gc
import importlib.metadata
import json
import os
from pathlib import Path
from time import perf_counter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", default="bf66a8244401a8e26d2ff429aa82df8550a289e5")
    parser.add_argument("--compute-dtype", choices=["float16", "bfloat16"], default="bfloat16")
    parser.add_argument("--keep-vision-full-precision", action="store_true")
    parser.add_argument("--prompt", default="Describe this image in a few sentences.")
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error("Choose an existing image crop.")
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    import psutil
    import torch
    from PIL import Image
    from transformers import AutoModelForImageTextToText, AutoProcessor, BitsAndBytesConfig

    report = {
        "model": "ibm-granite/granite-vision-3.3-2b", "revision": args.revision,
        "image": str(args.image.resolve()), "status": "initializing",
        "quantization": "bitsandbytes 4-bit NF4 with double quantization",
        "compute_dtype": args.compute_dtype, "device": "cuda:0", "max_new_tokens": 200,
        "keep_vision_full_precision": args.keep_vision_full_precision,
        "generation_time_budget_seconds": 120,
        "prompt": args.prompt,
        "scope": "Single image model probe. Not a full-document or retrieval accuracy benchmark.",
        "versions": {p: importlib.metadata.version(p) for p in [
            "torch", "transformers", "accelerate", "bitsandbytes",
        ]},
    }

    def save():
        (args.output / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    model = inputs = generated = processor = image = None
    try:
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA-enabled PyTorch and an available GPU are required.")
        torch.set_num_threads(4)
        dtype = getattr(torch, args.compute_dtype)
        if dtype == torch.bfloat16 and not torch.cuda.is_bf16_supported():
            raise RuntimeError("This GPU/runtime does not support bfloat16.")
        free, total = torch.cuda.mem_get_info()
        report.update({
            "gpu": torch.cuda.get_device_name(0),
            "vram_free_gib_before": round(free / 1024**3, 3),
            "vram_total_gib": round(total / 1024**3, 3),
            "ram_available_gib_before": round(psutil.virtual_memory().available / 1024**3, 3),
        })
        if free < 3.5 * 1024**3:
            raise RuntimeError("Less than 3.5 GiB of GPU memory is free; skipping model load.")
        save()
        started = perf_counter()
        processor = AutoProcessor.from_pretrained(
            report["model"], revision=args.revision, local_files_only=True,
        )
        print("Loading cached Granite Vision in 4-bit on RTX GPU...", flush=True)
        quantization = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=dtype, bnb_4bit_use_double_quant=True,
            llm_int8_skip_modules=["model.vision_tower", "model.multi_modal_projector", "lm_head"]
            if args.keep_vision_full_precision else None,
        )
        model = AutoModelForImageTextToText.from_pretrained(
            report["model"], revision=args.revision, local_files_only=True,
            quantization_config=quantization, device_map={"": 0},
            dtype=dtype, attn_implementation="sdpa",
        ).eval()
        torch.cuda.synchronize()
        report["model_load_seconds"] = round(perf_counter() - started, 2)
        report["model_footprint_gib"] = round(model.get_memory_footprint() / 1024**3, 3)
        # Explicit single-device loading need not attach hf_device_map in v5.
        report["parameter_devices"] = sorted({str(p.device) for p in model.parameters()})
        quantized_names = [name for name, module in model.named_modules()
                           if module.__class__.__name__ == "Linear4bit"]
        report["quantized_layer_count"] = len(quantized_names)
        report["quantized_vision_layers"] = [name for name in quantized_names
            if "vision_tower" in name or "multi_modal_projector" in name]
        if args.keep_vision_full_precision and report["quantized_vision_layers"]:
            raise RuntimeError("Vision-layer exclusion was not applied; refusing a mislabeled comparison.")
        report["status"] = "loaded"
        save()

        image = Image.open(args.image).convert("RGB")
        report["image_size"] = list(image.size)
        image.save(args.output / "input.png")
        messages = [{"role": "user", "content": [
            {"type": "image"}, {"type": "text", "text": report["prompt"]},
        ]}]
        prompt = processor.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
        inputs = processor(text=prompt, images=image, return_tensors="pt")
        inputs = inputs.to("cuda:0", dtype=dtype)
        report["input_tokens"] = inputs["input_ids"].shape[-1]
        torch.cuda.reset_peak_memory_stats()
        print("Generating one chart description (200-token cap)...", flush=True)
        started = perf_counter()
        with torch.inference_mode():
            generated = model.generate(
                **inputs, max_new_tokens=report["max_new_tokens"],
                max_time=report["generation_time_budget_seconds"],
                do_sample=False, use_cache=True,
                pad_token_id=processor.tokenizer.pad_token_id,
            )
        torch.cuda.synchronize()
        token_ids = generated[0, inputs["input_ids"].shape[-1]:]
        text = processor.decode(token_ids, skip_special_tokens=True).strip()
        report.update({
            "status": "completed" if text else "completed_empty",
            "generation_seconds": round(perf_counter() - started, 2),
            "generated_tokens": token_ids.numel(), "text": text,
            "generated_token_ids": token_ids.tolist(),
            "hit_token_cap": token_ids.numel() >= report["max_new_tokens"],
            "peak_gpu_allocated_gib": round(torch.cuda.max_memory_allocated() / 1024**3, 3),
            "peak_gpu_reserved_gib": round(torch.cuda.max_memory_reserved() / 1024**3, 3),
        })
        save()
        print(json.dumps(report, indent=2), flush=True)
        return 0 if text else 2
    except Exception as exc:
        report.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        save()
        print(report["error"], flush=True)
        return 2
    finally:
        inputs = generated = model = processor = image = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


if __name__ == "__main__":
    raise SystemExit(main())
