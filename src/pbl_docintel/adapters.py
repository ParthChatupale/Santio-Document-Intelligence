"""A small adapter contract: host systems can keep their own parsers."""

import json
from pathlib import Path
from typing import Any, Protocol

from .evidence import build_index, build_index_from_bytes
from .schema import EvidenceIndex


class DocumentAdapter(Protocol):
    def adapt(self, source: Any) -> EvidenceIndex:
        """Return a normalized index, preserving actual evidence precision."""
        ...


class DoclingAdapter:
    def __init__(self, source_pdf: Path | None = None):
        self.source_pdf = source_pdf

    def adapt(self, source: Any) -> EvidenceIndex:
        if isinstance(source, (str, Path)):
            return build_index(Path(source), self.source_pdf)
        if isinstance(source, bytes):
            return build_index_from_bytes(source, source_pdf=self.source_pdf)
        if hasattr(source, "export_to_dict"):
            source = source.export_to_dict()
        if not isinstance(source, dict):
            raise TypeError("Docling adapter expects JSON path, bytes, dictionary, or DoclingDocument")
        # In-memory inputs get a canonical serialization identity. This may
        # differ from the byte hash of a separately saved Docling JSON file.
        raw = json.dumps(source, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
        return build_index_from_bytes(raw, source_pdf=self.source_pdf)


class EvidenceAdapter:
    """Accept our normalized contract from any upstream provider."""
    def adapt(self, source: Any) -> EvidenceIndex:
        if isinstance(source, EvidenceIndex):
            return EvidenceIndex.model_validate_json(source.model_dump_json())
        if isinstance(source, Path):
            return EvidenceIndex.model_validate_json(source.read_bytes())
        if isinstance(source, (str, bytes)):
            return EvidenceIndex.model_validate_json(source)
        if isinstance(source, dict):
            return EvidenceIndex.model_validate_json(json.dumps(source, allow_nan=False))
        raise TypeError("Expected a normalized evidence index, dictionary, JSON, or Path")


def index_document(source: Any, adapter: DocumentAdapter | None = None) -> EvidenceIndex:
    """Index without requiring downstream apps to use a specific parser."""
    index = (adapter or DoclingAdapter()).adapt(source)
    return EvidenceAdapter().adapt(index)
