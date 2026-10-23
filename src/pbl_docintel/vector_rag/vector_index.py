"""Step 3: embed saved chunks locally and store/query them with PostgreSQL pgvector.

No PDF conversion, vision inference, answer generation or hosted API calls.
Run --help for index and search commands. Model weights must already be cached.
"""

import argparse
from datetime import datetime, timezone
import gc
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

from .chunker import TOKENIZER_MODEL, TOKENIZER_REVISION, MODEL_MAX_TOKENS

DIMENSIONS = 384
from .config import SANDBOX_ROOT

ROOT = SANDBOX_ROOT
SCHEMA_PATH = Path(__file__).with_name("vector_schema.sql")


class DatabaseConnectionError(RuntimeError):
    """Database connection failure with the password removed from its message."""


def load_chunks(path: Path) -> tuple[list[dict], dict, str]:
    """Read JSONL plus its validation report and identify this exact dataset/model."""
    path = path.resolve(strict=True)
    report = json.loads((path.parent / "chunking_report.json").read_text(encoding="utf-8"))
    if report.get("violations") or report.get("status") != "ready_for_embedding_review":
        raise ValueError("Chunk validation did not pass. Review chunking_report.json first.")
    if (report.get("tokenizer_model"), report.get("tokenizer_revision_resolved")) != (
        TOKENIZER_MODEL, TOKENIZER_REVISION
    ):
        raise ValueError("These chunks use a different tokenizer. Regenerate them with the current chunker.")
    content = path.read_bytes()
    chunks = [json.loads(line) for line in content.decode("utf-8").splitlines() if line.strip()]
    if not chunks or len(chunks) != report["chunks"]:
        raise ValueError("Chunk count does not match its report.")
    ids = [c["chunk_id"] for c in chunks]
    if len(set(ids)) != len(ids):
        raise ValueError("Chunk IDs must be unique within this dataset.")
    if any(not c.get("contextualized_text", "").strip() or not c.get("source_refs") for c in chunks):
        raise ValueError("Each chunk needs embedding text and source references.")
    identity = {
        "source_sha256": report["source_sha256"],
        "chunks_sha256": hashlib.sha256(content).hexdigest(),
        "model": TOKENIZER_MODEL, "revision": TOKENIZER_REVISION,
        "dimensions": DIMENSIONS, "pooling": "CLS", "normalization": "L2",
        "compute_dtype": "float32", "format_version": 1,
    }
    index_id = "r2-" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    manifest = {"identity": identity, "chunks_file": str(path), "chunking_report": report}
    return chunks, manifest, index_id


def connect_database(env_file: Path):
    """Open the sandbox connection without hardcoding or displaying its password."""
    import psycopg
    from dotenv import dotenv_values
    from pgvector.psycopg import register_vector

    settings = dotenv_values(env_file)
    required = ["PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"]
    if any(not settings.get(key) for key in required):
        raise ValueError("Database settings are incomplete. Check the sandbox .env file.")
    connection = None
    try:
        connection = psycopg.connect(
            host=settings["PGHOST"], port=int(settings["PGPORT"]),
            dbname=settings["PGDATABASE"], user=settings["PGUSER"], password=settings["PGPASSWORD"],
            connect_timeout=int(settings.get("PGCONNECT_TIMEOUT", "5")),
            application_name="santio-vector-index", autocommit=True,
        )
        register_vector(connection)
        return connection
    except Exception as exc:
        if connection is not None:
            connection.close()
        raise DatabaseConnectionError(str(exc).replace(settings["PGPASSWORD"], "[redacted]")) from None


def load_model(device: str = "auto"):
    """Load the pinned local tokenizer/model; auto selects CUDA when available."""
    import torch
    from transformers import AutoModel, AutoTokenizer

    if device == "auto":
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
    elif device == "cuda":
        device = "cuda:0"
    if device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable. Choose --device cpu or fix the CUDA installation.")
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_MODEL, revision=TOKENIZER_REVISION,
                                              local_files_only=True)
    model = AutoModel.from_pretrained(
        TOKENIZER_MODEL, revision=TOKENIZER_REVISION, local_files_only=True,
        dtype=torch.float32, attn_implementation="sdpa",
    ).to(device).eval()
    if model.config.hidden_size != DIMENSIONS or model.config.max_position_embeddings != MODEL_MAX_TOKENS:
        raise RuntimeError("Loaded model does not match the configured vector dimensions/context limit.")
    return tokenizer, model


def embed_texts(texts: list[str], tokenizer, model, batch_size: int = 8, progress=None):
    """Encode text batches, take CLS embeddings, and L2-normalize the vectors."""
    import numpy as np
    import torch

    if not texts or batch_size < 1 or any(not text.strip() for text in texts):
        raise ValueError("Provide nonempty texts and a positive batch size.")
    vectors, lengths = [], []
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        inputs = tokenizer(batch, padding=True, truncation=False, return_tensors="pt")
        counts = inputs["attention_mask"].sum(dim=1).tolist()
        if max(counts) > MODEL_MAX_TOKENS:
            raise ValueError(f"Batch starting at {start} exceeds the model window; text was not truncated.")
        inputs = inputs.to(model.device)
        with torch.inference_mode():
            pooled = model(**inputs).last_hidden_state[:, 0].float()
            if not torch.isfinite(pooled).all() or (pooled.norm(dim=1) < 1e-8).any():
                raise RuntimeError("Model returned an invalid or zero embedding.")
            normalized = torch.nn.functional.normalize(pooled, dim=1)
        vectors.append(normalized.cpu().numpy())
        lengths.extend(counts)
        print(f"Embedded {min(start + batch_size, len(texts))}/{len(texts)} texts", file=sys.stderr, flush=True)
        if progress:
            progress(min(start + batch_size, len(texts)), len(texts))
    result = np.concatenate(vectors)
    if result.shape != (len(texts), DIMENSIONS) or not np.allclose(np.linalg.norm(result, axis=1), 1, atol=1e-5):
        raise RuntimeError("Embedding dimension/normalization validation failed.")
    return result, lengths


def store_embeddings(connection, index_id: str, chunks: list[dict], vectors, manifest: dict) -> dict:
    """Atomically insert and read back every row; identical reruns create no duplicates."""
    import numpy as np
    from pgvector import Vector
    from psycopg.types.json import Jsonb

    if vectors.shape != (len(chunks), DIMENSIONS) or not np.isfinite(vectors).all():
        raise ValueError("Vectors do not match the input chunks.")
    if not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5):
        raise ValueError("Expected normalized vectors.")
    metadata = [{k: v for k, v in c.items() if k not in {
        "chunk_id", "text", "contextualized_text", "tokens_with_special_tokens"
    }} for c in chunks]
    # Nothing is committed until all vectors and evidence metadata pass read-back checks.
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
            cursor.execute("""
                INSERT INTO rag.vector_indexes
                    (index_id, model_name, model_revision, dimensions, chunk_count, manifest)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (index_id) DO NOTHING
            """, (index_id, TOKENIZER_MODEL, TOKENIZER_REVISION, DIMENSIONS, len(chunks), Jsonb(manifest)))
            cursor.execute("SELECT manifest FROM rag.vector_indexes WHERE index_id = %s", (index_id,))
            if cursor.fetchone()[0]["identity"] != manifest["identity"]:
                raise RuntimeError("Existing index identity differs; refusing to overwrite it.")
            cursor.executemany("""
                INSERT INTO rag.chunks (index_id, chunk_id, ordinal, text, contextualized_text,
                                        token_count, metadata, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (index_id, chunk_id) DO NOTHING
            """, [(index_id, c["chunk_id"], i, c["text"], c["contextualized_text"],
                   c["tokens_with_special_tokens"], Jsonb(metadata[i]), Vector(vectors[i]))
                  for i, c in enumerate(chunks)])
            inserted = cursor.rowcount
            cursor.execute("""
                SELECT chunk_id, text, contextualized_text, token_count, metadata, embedding
                FROM rag.chunks WHERE index_id = %s ORDER BY ordinal
            """, (index_id,))
            rows = cursor.fetchall()
            if len(rows) != len(chunks):
                raise RuntimeError("Stored chunk count differs from input; rolling back.")
            for i, (row, chunk) in enumerate(zip(rows, chunks)):
                if row[:5] != (chunk["chunk_id"], chunk["text"], chunk["contextualized_text"],
                               chunk["tokens_with_special_tokens"], metadata[i]):
                    raise RuntimeError("Stored text or source metadata differs; rolling back.")
                if not np.allclose(row[5].to_list(), vectors[i], atol=1e-7, rtol=1e-6):
                    raise RuntimeError("Stored vector differs; rolling back.")
    return {"stored_chunks": len(rows), "new_rows": inserted,
            "existing_rows_reused": len(rows) - inserted, "all_rows_read_back_and_verified": True}


def search(connection, index_id: str, query_vector, top_k: int = 5) -> list[dict]:
    """Find nearest chunks in one compatible index using exact cosine distance."""
    import numpy as np
    from pgvector import Vector

    query_vector = np.asarray(query_vector, dtype=np.float32)
    if query_vector.shape != (DIMENSIONS,) or not np.isfinite(query_vector).all() or np.linalg.norm(query_vector) < 1e-8:
        raise ValueError("Query must be a finite, nonzero 384-dimensional vector.")
    if not 1 <= top_k <= 50:
        raise ValueError("top_k must be between 1 and 50.")
    with connection.cursor() as cursor:
        cursor.execute("SELECT model_name, model_revision FROM rag.vector_indexes WHERE index_id = %s", (index_id,))
        identity = cursor.fetchone()
        if identity != (TOKENIZER_MODEL, TOKENIZER_REVISION):
            raise ValueError("Index is missing or uses a different model/revision.")
        cursor.execute("""
            SELECT chunk_id, contextualized_text, metadata, embedding <=> %s AS distance
            FROM rag.chunks WHERE index_id = %s ORDER BY distance, ordinal LIMIT %s
        """, (Vector(query_vector), index_id, top_k))
        return [{"chunk_id": row[0], "contextualized_text": row[1], "metadata": row[2],
                 "cosine_distance": row[3], "cosine_similarity": 1 - row[3]} for row in cursor.fetchall()]


def build_index(chunks_file: Path, env_file: Path, *, device: str = "auto", batch_size: int = 8, progress=None) -> dict:
    """Run validation, local embedding, database storage and a self-neighbor check."""
    import torch

    started = perf_counter()
    chunks, manifest, index_id = load_chunks(chunks_file)
    tokenizer = model = vectors = None
    try:
        with connect_database(env_file) as connection:
            print(f"Preparing {len(chunks)} chunks for index {index_id}", flush=True)
            tokenizer, model = load_model(device)
            if model.device.type == "cuda":
                torch.cuda.reset_peak_memory_stats()
            embedding_started = perf_counter()
            vectors, counts = embed_texts([c["contextualized_text"] for c in chunks], tokenizer, model, batch_size, progress=progress)
            embedding_seconds = perf_counter() - embedding_started
            if counts != [c["tokens_with_special_tokens"] for c in chunks]:
                raise ValueError("Actual token counts differ from the chunking report; regenerate chunks.")
            stored = store_embeddings(connection, index_id, chunks, vectors, manifest)
            neighbors = search(connection, index_id, vectors[0], top_k=1)
            if not neighbors or abs(neighbors[0]["cosine_distance"]) > 1e-5:
                raise RuntimeError("Stored-vector self-neighbor check failed.")
            return {
                "status": "success", "index_id": index_id, "database": connection.info.dbname,
                "chunks_table": "rag.chunks", "model": TOKENIZER_MODEL, "revision": TOKENIZER_REVISION,
                "device": str(model.device), "dimensions": DIMENSIONS, "pooling": "CLS",
                "normalization": "L2", "batch_size": batch_size, **stored,
                "embedding_seconds": round(embedding_seconds, 3),
                "total_seconds": round(perf_counter() - started, 3),
                "peak_gpu_allocated_mib": round(torch.cuda.max_memory_allocated() / 1024**2, 2)
                    if model.device.type == "cuda" else None,
                "self_neighbor_check": "passed", "retrieval_accuracy_evaluated": False,
                "chunking_review_notes": manifest["chunking_report"]["review_notes"],
            }
    finally:
        tokenizer = model = vectors = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def main() -> int:
    """Read terminal arguments and run indexing or passage search."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    sub = parser.add_subparsers(dest="command", required=True)
    index = sub.add_parser("index", help="Generate and store embeddings for a chunks.jsonl file")
    index.add_argument("chunks", type=Path)
    index.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    index.add_argument("--batch-size", type=int, default=8)
    index.add_argument("--report", type=Path)
    query = sub.add_parser("search", help="Retrieve passages; does not generate an answer")
    query.add_argument("--index-id", required=True)
    query.add_argument("--query", required=True)
    query.add_argument("--top-k", type=int, default=5)
    query.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    args = parser.parse_args()
    try:
        if args.command == "index":
            if args.batch_size < 1:
                parser.error("Batch size must be positive.")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            report_path = args.report or ROOT / "outputs" / f"vector-index-{stamp}" / "index_report.json"
            if report_path.exists():
                parser.error("Report already exists; choose a new report path.")
            report = build_index(args.chunks, args.env_file, device=args.device, batch_size=args.batch_size)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2), flush=True)
            print(f"Report saved: {report_path}", flush=True)
        else:
            tokenizer, model = load_model(args.device)
            vectors, _ = embed_texts([args.query], tokenizer, model, batch_size=1)
            with connect_database(args.env_file) as connection:
                results = search(connection, args.index_id, vectors[0], args.top_k)
            print(json.dumps({"query": args.query, "index_id": args.index_id,
                              "results": results}, indent=2, ensure_ascii=True), flush=True)
    except Exception as exc:
        print(f"Vector index failed: {exc}", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
