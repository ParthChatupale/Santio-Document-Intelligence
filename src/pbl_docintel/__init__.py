"""Evidence-backed research result records built on saved Docling documents."""

SCHEMA_VERSION = "0.1.0"

from .adapters import DoclingAdapter, DocumentAdapter, EvidenceAdapter, index_document
from .rag import rag_chunks, resolve_evidence, to_langchain_documents, write_rag_jsonl
from .schema import EvidenceIndex, ResultCollection, ResultRecord
from .validation import check_collection as validate_results
from .understanding import analyze, answer
from .models import HTTPJSONModel

__all__ = ["DoclingAdapter", "DocumentAdapter", "EvidenceAdapter", "EvidenceIndex",
           "ResultCollection", "ResultRecord", "index_document", "rag_chunks",
           "resolve_evidence", "to_langchain_documents", "validate_results", "write_rag_jsonl",
           "analyze", "answer", "HTTPJSONModel"]
