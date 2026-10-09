"""Index source text and table cells without rerunning Docling or altering it."""

import hashlib
import json
import re
from pathlib import Path

from .schema import Cell, DocumentIdentity, EvidenceIndex, EvidenceUnit, Location

NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
SINGLE_NUMBER = re.compile(rf"^{NUMBER}$")
MULTIPLE_NUMBERS = re.compile(rf"^{NUMBER}(?:\s+{NUMBER})+$")


def cell_id(item_ref: str, index: int) -> str:
    """Our evidence ID, not a native Docling JSON pointer."""
    return f"{item_ref}::cell:{index}"


def _refs(item: dict, key: str) -> list[str]:
    return [value["$ref"] for value in item.get(key, [])]


def build_index(json_path: Path, source_pdf: Path | None = None) -> EvidenceIndex:
    return build_index_from_bytes(json_path.read_bytes(), json_path.name, source_pdf)


def build_index_from_bytes(raw: bytes, json_filename: str = "in-memory.docling.json",
                           source_pdf: Path | None = None) -> EvidenceIndex:
    """Shared adapter implementation; no Docling import or model inference."""
    document = json.loads(raw)
    if not isinstance(document, dict) or document.get("schema_name") != "DoclingDocument":
        raise ValueError("Expected an exported DoclingDocument JSON")
    source_filename = (document.get("origin") or {}).get("filename") or document["name"]
    source_hash = None
    if source_pdf is not None:
        if source_pdf.name != source_filename:
            raise ValueError("Source PDF filename does not match the Docling origin")
        source_hash = hashlib.sha256(source_pdf.read_bytes()).hexdigest()
    pages = {
        str(page["page_no"]): page["size"] for page in document.get("pages", {}).values()
    }
    identity = DocumentIdentity(
        document_id=hashlib.sha256(raw).hexdigest(),
        docling_json_filename=json_filename,
        source_filename=source_filename,
        source_sha256=source_hash,
        docling_schema_version=document["version"],
        pages=pages,
    )
    units: dict[str, EvidenceUnit] = {}
    for collection, kind in (("texts", "text"), ("tables", "table"), ("pictures", "picture")):
        for item in document.get(collection, []):
            ref = item["self_ref"]
            if ref in units:
                raise ValueError(f"Duplicate item reference: {ref}")
            locations = [Location(**prov) for prov in item.get("prov", [])]
            if any(str(loc.page_no) not in pages for loc in locations):
                raise ValueError(f"Invalid page provenance: {ref}")
            issues = []
            if not locations:
                issues.append("missing_page_provenance")
            if kind == "text" and not item.get("text", "").strip():
                issues.append("empty_extracted_text")
            units[ref] = EvidenceUnit(
                evidence_id=ref, item_ref=ref, kind=kind,
                label=item["label"], text=item.get("text", ""), locations=locations,
                context={key: _refs(item, key) for key in ("captions", "footnotes")},
                issues=issues,
            )
    for table in document.get("tables", []):
        ref = table["self_ref"]
        table_unit = units[ref]
        table_cells = []
        if not table["data"]["table_cells"] or not table["data"]["num_rows"] or not table["data"]["num_cols"]:
            table_unit.issues.append("empty_table_structure")
        for i, raw_cell in enumerate(table["data"]["table_cells"]):
            info = Cell(
                index=i, row_start=raw_cell["start_row_offset_idx"],
                row_end=raw_cell["end_row_offset_idx"],
                col_start=raw_cell["start_col_offset_idx"],
                col_end=raw_cell["end_col_offset_idx"],
                **{key: raw_cell.get(key, False) for key in
                   ("column_header", "row_header", "row_section")},
            )
            if info.row_end > table["data"]["num_rows"] or info.col_end > table["data"]["num_cols"]:
                raise ValueError(f"Out-of-bounds cell: {cell_id(ref, i)}")
            issues = []
            unique_pages = {loc.page_no for loc in table_unit.locations}
            # Cell boxes do not identify a page in this export. Only bind them
            # to a page when the table has exactly one possible page.
            if len(unique_pages) == 1 and raw_cell.get("bbox") is not None:
                locations = [Location(page_no=next(iter(unique_pages)),
                                      bbox=raw_cell["bbox"], granularity="cell")]
            else:
                locations = [loc.model_copy(update={"granularity": "table"})
                             for loc in table_unit.locations]
                issues.append("cell_location_not_resolved")
            if MULTIPLE_NUMBERS.fullmatch(raw_cell["text"].strip()):
                issues.append("multiple_numeric_values")
            if not info.column_header and not info.row_header and not info.row_section:
                if info.row_end - info.row_start > 1 or info.col_end - info.col_start > 1:
                    issues.append("spanning_data_cell")
            unit = EvidenceUnit(
                evidence_id=cell_id(ref, i), item_ref=ref, kind="table_cell",
                label="table_cell", text=raw_cell["text"], locations=locations,
                cell=info, issues=issues,
                context={key: list(table_unit.context[key]) for key in ("captions", "footnotes")},
            )
            units[unit.evidence_id] = unit
            table_cells.append(unit)
        table_unit.context["cells"] = [c.evidence_id for c in table_cells]
        for unit in table_cells:
            c = unit.cell
            unit.context["column_headers"] = [
                other.evidence_id for other in table_cells
                if other.cell.column_header and other.cell.row_end <= c.row_start
                and other.cell.col_start < c.col_end and other.cell.col_end > c.col_start
            ]
            unit.context["row_headers"] = [
                other.evidence_id for other in table_cells
                if other.cell.row_header and other.cell.row_start < c.row_end
                and other.cell.row_end > c.row_start and other.evidence_id != unit.evidence_id
            ]
            # Some exports omit row_header flags. Keep first-column labels as
            # candidates, separately from Docling's explicit row headers.
            unit.context["row_labels"] = [
                other.evidence_id for other in table_cells
                if other.cell.col_start == 0 and not other.cell.column_header
                and not other.cell.row_section and other.cell.row_start < c.row_end
                and other.cell.row_end > c.row_start and other.evidence_id != unit.evidence_id
            ]
            prior_sections = [other for other in table_cells
                              if other.cell.row_section and other.cell.row_end <= c.row_start]
            if prior_sections:
                last_row = max(other.cell.row_start for other in prior_sections)
                unit.context["row_sections"] = [other.evidence_id for other in prior_sections
                                                if other.cell.row_start == last_row]
    for unit in units.values():
        for links in unit.context.values():
            if any(link not in units for link in links):
                raise ValueError(f"Unresolved context reference on {unit.evidence_id}")
    return EvidenceIndex(document=identity, units=units)
