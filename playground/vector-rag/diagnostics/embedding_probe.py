"""Check the cached R2 model on CUDA before implementing database indexing.

Follows the model's Transformers example: CLS-token pooling and L2 normalization.
Uses short synthetic examples; it is not a paper retrieval accuracy evaluation.
No database connection, hosted inference or additional model download is used.
"""

import argparse
import gc
import json
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chunker import TOKENIZER_MODEL, TOKENIZER_REVISION, MODEL_MAX_TOKENS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    import torch
    from transformers import AutoConfig, AutoModel, AutoTokenizer

    report = {"model": TOKENIZER_MODEL, "revision": TOKENIZER_REVISION,
              "pooling": "CLS token", "normalization": "L2", "dtype": "float32",
              "status": "initializing", "database_rows_written": 0,
              "scope": "Synthetic model execution/similarity check, not research-paper accuracy"}
    model = tokenizer = inputs = vectors = None
    try:
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable; this diagnostic specifically tests the GPU.")
        report["gpu"] = torch.cuda.get_device_name(0)
        tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_MODEL, revision=TOKENIZER_REVISION,
                                                  local_files_only=True)
        config = AutoConfig.from_pretrained(TOKENIZER_MODEL, revision=TOKENIZER_REVISION,
                                            local_files_only=True)
        print("Loading the cached R2 embedding model on CUDA...", flush=True)
        started = perf_counter()
        model = AutoModel.from_pretrained(
            TOKENIZER_MODEL, revision=TOKENIZER_REVISION, config=config,
            local_files_only=True, dtype=torch.float32, attn_implementation="sdpa",
        ).to("cuda:0").eval()
        torch.cuda.synchronize()
        report["load_seconds"] = round(perf_counter() - started, 3)
        texts = [
            "How does retrieval augmented generation use external documents?",
            "What is instruction fine tuning?",
            "Retrieval augmented generation retrieves relevant passages from external documents and supplies them to a language model to answer a question.",
            "Instruction fine tuning trains a language model on instruction and response examples to improve its ability to follow user instructions.",
        ]
        inputs = tokenizer(texts, padding=True, truncation=False, return_tensors="pt")
        lengths = inputs["attention_mask"].sum(dim=1).tolist()
        if max(lengths) > MODEL_MAX_TOKENS:
            raise RuntimeError("Input exceeds model context; this diagnostic never silently truncates.")
        inputs = inputs.to("cuda:0")
        torch.cuda.reset_peak_memory_stats()
        started = perf_counter()
        with torch.inference_mode():
            vectors = torch.nn.functional.normalize(model(**inputs).last_hidden_state[:, 0].float(), dim=1)
            single_input = tokenizer([texts[0]], return_tensors="pt").to("cuda:0")
            single_vector = torch.nn.functional.normalize(
                model(**single_input).last_hidden_state[:, 0].float(), dim=1)
        torch.cuda.synchronize()
        if vectors.shape != (4, 384) or not torch.isfinite(vectors).all():
            raise RuntimeError("Embedding shape/finite-value check failed.")
        if not torch.allclose(vectors.norm(dim=1), torch.ones(4, device="cuda:0"), atol=1e-5):
            raise RuntimeError("Embedding normalization check failed.")
        difference = (vectors[0] - single_vector[0]).abs().max().item()
        if difference > 1e-4:
            raise RuntimeError("Batch padding changed the embedding beyond tolerance.")
        similarities = vectors[:2] @ vectors[2:].T
        top = similarities.argmax(dim=1).tolist()
        report.update(status="PASS" if top == [0, 1] else "similarity_check_failed",
                      embedding_shape=list(vectors.shape), input_tokens=lengths,
                      compute_seconds=round(perf_counter() - started, 3),
                      model_footprint_mib=round(model.get_memory_footprint() / 1024**2, 2),
                      peak_gpu_allocated_mib=round(torch.cuda.max_memory_allocated() / 1024**2, 2),
                      batch_vs_single_max_absolute_difference=difference,
                      synthetic_cosine_similarities=similarities.cpu().tolist(),
                      synthetic_expected_top_passages=[0, 1], synthetic_actual_top_passages=top)
        (args.output / "sample_embeddings.json").write_text(json.dumps({"texts": texts,
            "vectors": vectors.cpu().tolist()}, indent=2), encoding="utf-8")
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    finally:
        model = tokenizer = inputs = vectors = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
