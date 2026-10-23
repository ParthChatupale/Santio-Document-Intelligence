"""Check caption routing with real Docling objects; optionally run one GPU fallback.

No PDF conversion or original export is changed. All outputs go to a new folder.
"""

import argparse
import builtins
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from granite_picture_descriptions import describe_pictures
from docling_core.types.doc import DocItemLabel, DoclingDocument, RefItem


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gpu", action="store_true", help="Also generate for real captionless pictures")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source_hash = hashlib.sha256(args.document.read_bytes()).hexdigest()
    document = DoclingDocument.load_from_json(args.document)
    checks = []

    def run(name, doc):
        out = args.output / name
        out.mkdir()
        return describe_pictures(doc, out)

    # An all-caption document must work without importing either GPU dependency.
    original_import = builtins.__import__

    def guard(name, *a, **kw):
        if name.split(".")[0] in {"torch", "transformers"}:
            raise AssertionError("Caption reuse unexpectedly imported a model dependency")
        return original_import(name, *a, **kw)

    fixture = DoclingDocument(name="caption-routing")
    cap = fixture.add_text(label=DocItemLabel.CAPTION, text="An author caption.")
    fixture.add_picture(caption=cap)
    with patch("builtins.__import__", side_effect=guard):
        r = run("caption-no-gpu-imports", fixture)
    assert r["status"] == "captions_only" and r["captions_reused"] == 1
    assert r["model_loaded"] is False and r["generated"] == 0
    assert r["items"][0]["text_source"] == "extracted_caption"
    assert fixture.pictures[0].meta is None  # Never relabel authored text as AI metadata.
    checks.append("Nonempty caption reused without model imports or generated metadata")

    # Use all real pictures whose linked captions contain text; preserve source file.
    captioned = document.model_copy(deep=True)
    captioned.pictures = [p for p in captioned.pictures if p.captions and any(
        ref.resolve(captioned).text.strip() for ref in p.captions
    )]
    real_before = captioned.export_to_dict()
    with patch("builtins.__import__", side_effect=guard):
        real = run("real-document-captions", captioned)
    assert real["captions_reused"] == len(captioned.pictures)
    assert real["generated"] == 0 and not real["model_loaded"]
    assert captioned.export_to_dict() == real_before
    checks.append(f"All {len(captioned.pictures)} real captioned pictures reused; captioned document unchanged")

    # Empty, absent and broken references must reach the fallback, never count as captions.
    import torch
    for name in ["missing", "whitespace", "broken"]:
        doc = DoclingDocument(name=name)
        pic = doc.add_picture()
        if name == "whitespace":
            c = doc.add_text(label=DocItemLabel.CAPTION, text="  \n  ")
            pic.captions = [c.get_ref()]
        elif name == "broken":
            pic.captions = [RefItem(cref="#/texts/99999")]
        with patch("torch.cuda.is_available", return_value=False):
            r = run(name, doc)
        assert r["captions_reused"] == 0 and r["failed"] == 1
        assert r["items"][0]["fallback_reason"] == "no_nonempty_caption_detected"
        if name == "broken":
            assert r["items"][0]["caption_resolution_errors"]
        checks.append(f"{name}: fallback selected; unavailable CUDA explicitly reported")

    # Use real missing-caption pictures rather than assuming every picture has one.
    if args.gpu:
        clean = DoclingDocument.load_from_json(args.document)
        # Discard previous experimental generated descriptions in this test copy only.
        for pic in clean.pictures:
            pic.meta = None
        r = run("real-document-fallback", clean)
        assert r["captions_reused"] == len(captioned.pictures)
        assert r["generated"] == len(clean.pictures) - len(captioned.pictures)
        assert r["failed"] == 0 and r["model_loaded"]
        for pic, entry in zip(clean.pictures, r["items"]):
            if entry["status"] == "caption_reused":
                assert pic.meta is None
            else:
                assert entry["text_source"] == "ai_description"
                assert pic.meta.description.created_by.startswith("ibm-granite/")
        clean.save_as_json(args.output / "real-document-fallback" / "document.json")
        checks.append("Actual missing-caption pictures generated on CUDA; captioned pictures receive no AI metadata")

    assert hashlib.sha256(args.document.read_bytes()).hexdigest() == source_hash
    result = {"status": "PASS", "source_sha256": source_hash, "checks": checks}
    (args.output / "checks.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
