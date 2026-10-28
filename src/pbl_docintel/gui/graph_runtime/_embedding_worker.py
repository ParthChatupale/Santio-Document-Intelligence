"""Private JSON-lines worker: reuse cached Granite/CUDA in the MAIN environment.

This keeps a second PyTorch installation out of the GraphRAG environment.
No API credentials or remote inference are used. Stdout is protocol data only.
"""
import contextlib
import json
import sys

from _common import EMBEDDING_MODEL, EMBEDDING_REVISION


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    with contextlib.redirect_stdout(sys.stderr):
        import torch
        from transformers import AutoModel, AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(EMBEDDING_MODEL, revision=EMBEDDING_REVISION, local_files_only=True)
        model = AutoModel.from_pretrained(EMBEDDING_MODEL, revision=EMBEDDING_REVISION,
                                         local_files_only=True, dtype=torch.float32,
                                         attn_implementation="sdpa")
        model = model.to("cuda:0" if torch.cuda.is_available() else "cpu").eval()
    for line in sys.stdin:
        try:
            texts = json.loads(line)["texts"]
            if not isinstance(texts, list) or not texts or any(not isinstance(t, str) or not t.strip() for t in texts):
                raise ValueError("Embedding input must be a nonempty list of nonempty strings.")
            vectors, counts = [], []
            for start in range(0, len(texts), 4):
                inputs = tokenizer(texts[start:start + 4], padding=True, truncation=False, return_tensors="pt")
                lengths = inputs["attention_mask"].sum(dim=1).tolist()
                if max(lengths) > 8192:
                    raise ValueError("Granite input exceeds 8192 tokens; no text was truncated.")
                with torch.inference_mode():
                    pooled = model(**inputs.to(model.device)).last_hidden_state[:, 0].float()
                    if not torch.isfinite(pooled).all() or (pooled.norm(dim=1) < 1e-8).any():
                        raise ValueError("Invalid embedding returned.")
                    normalized = torch.nn.functional.normalize(pooled, dim=1)
                if normalized.shape[1] != 384:
                    raise ValueError("Unexpected embedding dimensions.")
                vectors.extend(normalized.cpu().tolist())
                counts.extend(lengths)
            result = {"vectors": vectors, "tokens": sum(counts), "device": str(model.device)}
        except Exception as exc:
            result = {"error": str(exc)}
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
