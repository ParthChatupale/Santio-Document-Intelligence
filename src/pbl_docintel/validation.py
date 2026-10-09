"""Conservative attribution checks, not scientific or comparison verification."""

import re
from decimal import Decimal

from .evidence import SINGLE_NUMBER
from .schema import EvidenceIndex, ResultCollection, ResultRecord


def _normalized(text: str) -> str:
    return " ".join(text.replace("↑", "").replace("↓", "").split()).casefold()


def check_record(record: ResultRecord, index: EvidenceIndex) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    if record.document_id != index.document.document_id:
        return {"result_id": record.result_id, "outcome": "invalid",
                "errors": ["conversion_identity_mismatch"], "warnings": []}
    links = [record.value_evidence, record.method_evidence, *record.metric_evidence,
             *record.benchmark.evidence, *record.metric.definition_evidence]
    links.extend(link for condition in record.conditions for link in condition.evidence)
    for link in links:
        unit = index.units.get(link.evidence_id)
        if unit is None:
            errors.append(f"unknown_evidence:{link.evidence_id}")
        elif link.quote is not None and link.quote not in unit.text:
            errors.append(f"quote_not_found:{link.evidence_id}")
    if errors:
        return {"result_id": record.result_id, "outcome": "invalid",
                "errors": sorted(set(errors)), "warnings": warnings}
    value = index.units[record.value_evidence.evidence_id]
    method = index.units[record.method_evidence.evidence_id]
    if record.value.raw.strip() != value.text.strip():
        errors.append("raw_value_does_not_match_source_unit")
    if record.value.numeric is not None:
        if not SINGLE_NUMBER.fullmatch(value.text.strip()):
            warnings.append("numeric_assignment_requires_review")
        elif Decimal(value.text.strip()) != Decimal(str(record.value.numeric)):
            errors.append("numeric_value_mismatch")
    else:
        warnings.append("numeric_value_unresolved")
    warnings.extend(value.issues)
    if value.kind == "table_cell":
        if value.cell.column_header or value.cell.row_header or value.cell.row_section:
            errors.append("value_points_to_header")
        if "row_headers" not in value.context and "row_labels" not in value.context:
            warnings.append("method_row_context_missing")
        elif method.evidence_id not in value.context.get("row_headers", []):
            if method.evidence_id in value.context.get("row_labels", []):
                warnings.append("method_row_label_inferred")
            else:
                errors.append("method_not_in_value_row")
        if _normalized(method.text) != _normalized(record.method.reported):
            errors.append("method_label_mismatch")
        headers = [index.units[link.evidence_id] for link in record.metric_evidence]
        table_only = [h for h in headers if h.kind == "table" and h.item_ref == value.item_ref]
        if table_only:
            warnings.append("metric_requires_table_layout_review")
        if "column_headers" not in value.context:
            warnings.append("metric_column_context_missing")
        elif any(h.evidence_id not in value.context["column_headers"] and h not in table_only for h in headers):
            errors.append("metric_not_in_value_column")
        matched = [h for h in headers if _normalized(h.text) == _normalized(record.metric.name.reported)]
        if not matched:
            warnings.append("metric_header_not_unambiguous")
        for header in matched:
            if "↑" in header.text and record.metric.direction != "higher":
                errors.append("metric_direction_mismatch")
            if "↓" in header.text and record.metric.direction != "lower":
                errors.append("metric_direction_mismatch")
        # When a table names datasets in grouped headers, a caption mentioning
        # both datasets cannot establish which one owns this value column.
        dataset_headers = [index.units[eid] for eid in index.units[value.item_ref].context.get("cells", [])
                           if index.units[eid].cell.column_header
                           and _normalized(index.units[eid].text) ==
                           _normalized(record.benchmark.dataset.reported)]
        if dataset_headers:
            in_column = [h.evidence_id for h in dataset_headers
                         if h.evidence_id in value.context.get("column_headers", [])]
            if "column_headers" not in value.context:
                warnings.append("dataset_column_context_missing")
            elif not in_column:
                errors.append("dataset_not_in_value_column")
            elif not any(link.evidence_id in in_column for link in record.benchmark.evidence):
                warnings.append("dataset_column_header_not_cited")
    else:
        warnings.append("non_table_assignment_not_semantically_checked")
    dataset = record.benchmark.dataset.reported
    if not any(re.search(rf"(?<!\w){re.escape(dataset)}(?!\w)",
                         index.units[link.evidence_id].text, re.IGNORECASE)
               for link in record.benchmark.evidence):
        errors.append("dataset_name_not_found_in_evidence")
    # Finding a name is not sufficient to bind the dataset to a table column.
    if not any(link.evidence_id in value.context.get("captions", [])
               or link.evidence_id in value.context.get("column_headers", [])
               for link in record.benchmark.evidence):
        warnings.append("dataset_evidence_not_structurally_associated")
    if record.review.status == "needs_review":
        warnings.append("annotation_requests_review")
    return {"result_id": record.result_id,
            "outcome": "invalid" if errors else "needs_review" if warnings else "evidence_checks_passed",
            "errors": sorted(set(errors)), "warnings": sorted(set(warnings))}


def check_collection(collection: ResultCollection, index: EvidenceIndex) -> list[dict]:
    if collection.document_id != index.document.document_id:
        raise ValueError("Results belong to a different Docling conversion; references cannot be reused")
    return [check_record(record, index) for record in collection.records]
