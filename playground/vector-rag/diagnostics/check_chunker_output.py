"""Check real caption-first extraction through the chunker in three explicit modes."""

import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chunker import chunk_document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    raw = json.loads(args.document.read_text(encoding="utf-8"))
    source_hash = hashlib.sha256(args.document.read_bytes()).hexdigest()
    variants = {}
    for name, include_ai, formula in [("baseline", False, "original"),
                                      ("with-ai", True, "original"),
                                      ("document-formulas", True, "document")]:
        # The full report is saved on disk; keep the diagnostic terminal readable.
        with contextlib.redirect_stdout(io.StringIO()):
            report = chunk_document(args.document, args.output / name,
                                    include_ai_descriptions=include_ai, formula_text=formula)
        chunks = [json.loads(line) for line in (args.output / name / "chunks.jsonl").read_text(
            encoding="utf-8").splitlines()]
        assert not report["violations"]
        assert len({c["chunk_id"] for c in chunks}) == len(chunks)
        assert all(c["tokens_with_special_tokens"] <= 512 for c in chunks)
        assert report["pages_represented"] == sorted(map(int, raw["pages"]))
        assert report["caption_refs_represented"] == report["caption_refs_total"]
        for picture in raw["pictures"]:
            for caption in picture["captions"]:
                matching = [c for c in chunks if caption["$ref"] in c["source_refs"]]
                assert matching
                assert all(any(p["picture_ref"] == picture["self_ref"]
                               for p in c["picture_links"]) for c in matching)
        assert not any("data:image/" in c["contextualized_text"] for c in chunks)
        variants[name] = (report, chunks)
        print(f"{name}: {len(chunks)} chunks; token and caption/image-link checks passed.", flush=True)

    baseline, base_chunks = variants["baseline"]
    ai, ai_chunks = variants["with-ai"]
    document_formulas, formula_chunks = variants["document-formulas"]
    assert not any("ai_description" in c["text_sources"] for c in base_chunks)
    ai_refs = set(ai["included_ai_picture_refs"])
    assert ai_refs and not ai["unrepresented_ai_picture_refs"]
    for ref in ai_refs:
        picture = next(p for p in raw["pictures"] if p["self_ref"] == ref)
        text = picture["meta"]["description"]["text"]
        assert text in "\n".join(c["contextualized_text"] for c in ai_chunks)
        assert text not in "\n".join(c["contextualized_text"] for c in base_chunks)
        assert any("ai_description" in c["text_sources"] and ref in c["source_refs"] for c in ai_chunks)
    assert ai["picture_metadata_excluded"] < baseline["picture_metadata_excluded"]
    assert document_formulas["formulas_restored_to_original"] == 0
    assert baseline["formulas_restored_to_original"] > 0
    for item in raw["texts"]:
        if item["label"] == "formula" and item["orig"] and item["orig"] != item["text"]:
            assert item["text"] in "\n".join(c["text"] for c in formula_chunks)
            assert item["orig"] in "\n".join(c["text"] for c in base_chunks)
    assert hashlib.sha256(args.document.read_bytes()).hexdigest() == source_hash
    summary = {
        "status": "PASS", "source_sha256": source_hash,
        "checks": ["all final chunks <= 512 tokens", "all document pages represented",
                   "all caption refs represented", "caption chunks link to correct picture refs",
                   "AI fallback text excluded by default and included with attribution on opt-in",
                   "original/document formula modes preserve their selected input text",
                   "no image bytes in embedding text", "source JSON unchanged"],
        "variants": {name: {k: r[k] for k in ["chunks", "largest_encoded_chunk", "included_ai_picture_refs",
                                              "formula_text_policy", "source_tables_without_cells"]}
                     for name, (r, _) in variants.items()},
    }
    (args.output / "checks.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
