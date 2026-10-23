"""Resolve native GraphRAG records/citations to saved Docling items and PDF pages.

Resolution establishes traceability, not factual entailment. Whole-record and
community mappings are deliberately labelled as broad, rather than precise quotes.
"""
import json
from pathlib import Path
import re

from _common import read_json


def as_rows(value):
    if hasattr(value, "to_json"):
        return json.loads(value.to_json(orient="records"))
    if isinstance(value, list):
        return value
    return []


def load_tables(folder):
    import pandas as pd
    return {p.stem: pd.read_parquet(p) for p in (Path(folder) / "output").glob("*.parquet")}


def source_ledger(folder, tables=None):
    tables = tables or load_tables(folder)
    source_map = read_json(Path(folder) / "source_map.json")
    ledger = {}
    docs = {}
    for row in as_rows(tables.get("documents", [])):
        data = row.get("raw_data") or {}
        if isinstance(data, str):
            data = json.loads(data)
        ident = data.get("source_record_id", row.get("id"))
        if ident in source_map:
            docs[row["id"]] = {ident}
    for row in as_rows(tables.get("text_units", [])):
        markers = re.findall(r"(?m)^source_record_id:\s*([A-Za-z0-9:_-]+)", row["text"])
        found = set(markers).intersection(source_map)
        ids = row.get("document_ids") or row.get("document_id") or []
        if isinstance(ids, str):
            ids = [ids]
        for ident in ids:
            found.update(docs.get(ident, set()))
        ledger[("text_units", str(row["id"]))] = found
    for name in ["entities", "relationships", "communities"]:
        for row in as_rows(tables.get(name, [])):
            found = set()
            for ident in row.get("text_unit_ids") or []:
                found.update(ledger.get(("text_units", str(ident)), set()))
            ledger[(name, str(row["id"]))] = found
    by_community = {str(row["community"]): ledger.get(("communities", str(row["id"])), set())
                    for row in as_rows(tables.get("communities", []))}
    for row in as_rows(tables.get("community_reports", [])):
        ledger[("community_reports", str(row["id"]))] = by_community.get(str(row["community"]), set())
    return source_map, ledger


NAMES = {"sources": "text_units", "entities": "entities", "relationships": "relationships",
         "reports": "community_reports"}


def resolve_context(folder, context):
    tables = load_tables(folder)
    source_map, ledger = source_ledger(folder, tables)
    output = {}
    for category, value in context.items():
        name = NAMES.get(category.casefold())
        if not name:
            continue
        native = {str(row.get("human_readable_id")): row for row in as_rows(tables.get(name, []))}
        rows = []
        for record in as_rows(value):
            row = native.get(str(record.get("id")))
            found = ledger.get((name, str(row["id"])), set()) if row else set()
            sources = [source_map[r] for r in sorted(found)]
            rows.append({"citation_id": str(record.get("id")), "native_id": row["id"] if row else None,
                         "resolved": bool(sources), "docling_refs": sorted({r for s in sources for r in s["item_refs"]}),
                         "pages": sorted({p for s in sources for p in s["pages"]}),
                         "source_records": sources,
                         "scope": "whole_source_records; report mappings may span many passages",
                         "entailment_verified": False})
        output[category.casefold()] = rows
    return output


def check_citations(answer, resolved_context):
    matches = re.findall(r"\[Data:\s*([^\]]+)\]", answer, re.I)
    checked = []
    for group in matches:
        for name, ids in re.findall(r"([A-Za-z ]+)\s*\(([^)]*)\)", group):
            name = name.strip().casefold()
            rows = {r["citation_id"]: r for r in resolved_context.get(name, [])}
            for ident in re.findall(r"\b\d+\b", ids):
                found = rows.get(ident)
                checked.append({"category": name, "citation_id": ident,
                                "resolved": bool(found and found["resolved"]),
                                "docling_refs": found["docling_refs"] if found else [],
                                "pages": found["pages"] if found else []})
    return {"citations": checked, "all_cited_records_resolved": bool(checked) and all(c["resolved"] for c in checked),
            "note": "Checks native citation IDs against selected context and source mappings, not semantic entailment."}
