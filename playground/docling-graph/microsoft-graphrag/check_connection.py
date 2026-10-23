"""Checkpoint 2: exercise Microsoft's provider contracts with tiny real inputs.

Default: local environment/embedding checks only. --live additionally makes two
small NVIDIA requests. Saves replies and dimensions, never the credential.
"""
import argparse
from importlib.metadata import version
import math
from pathlib import Path
import sys

from _common import HERE, EMBEDDING_MODEL, EMBEDDING_REVISION, safe_error, stamp, write_json


def check(output, live=False):
    from pydantic import BaseModel
    from graphrag_llm.config import ModelConfig
    from graphrag_llm.completion import create_completion
    from graphrag_llm.embedding import create_embedding
    from _providers import configure
    report = {"python": sys.version.split()[0], "graphrag": version("graphrag"),
              "embedding_model": EMBEDDING_MODEL, "embedding_revision": EMBEDDING_REVISION,
              "live_completion_requested": live, "status": "running"}
    runtime = configure(output, max_calls=2, max_tokens=15000, max_seconds=300)
    try:
        model = create_embedding(ModelConfig(type="santio_granite", model_provider="local", model=EMBEDDING_MODEL))
        result = model.embedding(input=["A model is fine-tuned from a base model.", "A model is fine-tuned from a base model."])
        norms = [math.sqrt(sum(v * v for v in row)) for row in result.embeddings]
        if len(result.embeddings) != 2 or any(len(v) != 384 for v in result.embeddings) or any(abs(n - 1) > 1e-4 for n in norms):
            raise ValueError("Embedding batch contract or normalization failed.")
        if result.embeddings[0] != result.embeddings[1]:
            raise ValueError("Identical local inputs returned different vectors.")
        report["embedding"] = {"passed": True, "texts": 2, "dimensions": 384, "norms": norms,
                               "device": runtime.embedding_calls[-1]["device"]}
        if live:
            completion = create_completion(ModelConfig(type="santio_nvidia", model_provider="openai", model=runtime.model))
            reply = completion.completion(messages="Reply with just: Hi", max_completion_tokens=40)
            report["completion"] = {"passed": bool(reply.content.strip()), "reply": reply.content}
            class Fact(BaseModel):
                subject: str
                relation: str
                object: str
            structured = completion.completion(messages=[{"role": "user", "content":
                "Extract the explicit fact: Model Cedar was fine-tuned from Model Birch. Return JSON with subject, relation and object."}],
                response_format=Fact, max_completion_tokens=150)
            fact = structured.formatted_response
            if "Cedar" not in fact.subject or "Birch" not in fact.object:
                raise ValueError("Structured response parsed but did not preserve subject/object ownership.")
            report["structured_completion"] = {"passed": True, "reply": fact.model_dump()}
        report["status"] = "passed"
    except Exception as exc:
        report.update(status="failed", error=safe_error(exc, runtime.key))
    finally:
        runtime.save()
        runtime.close()
        write_json(Path(output) / "connection_report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, default=HERE / "runs" / ("connection-" + stamp()))
    args = parser.parse_args()
    import json
    report = check(args.output, args.live)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
