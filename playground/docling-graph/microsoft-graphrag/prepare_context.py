"""Versioned context-preserving view of an existing prepared Docling document.

Tables become row records with explicit column-header paths. Every bounded prose
part repeats the actual paper title/headings. Provenance stays in sidecar fields.
No model calls, PDF conversion, or changes to the original prepared directory.
"""
import argparse
from copy import deepcopy
from pathlib import Path

import tiktoken

from _common import digest, read_json, write_json


def prepare_context(prepared, output):
    prepared, output = Path(prepared).resolve(strict=True), Path(output).resolve()
    if output.exists():
        raise ValueError("Use a new preparation directory")
    old_report = read_json(prepared / "preparation_report.json")
    if digest(old_report["source"]) != old_report["source_sha256"]:
        raise ValueError("Docling source changed")
    old_records = read_json(prepared / "input/documents.json")
    old_map = read_json(prepared / "source_map.json")
    doc = read_json(old_report["source"])
    title = next((t["text"] for t in doc["texts"] if t["label"] == "title"),
                 old_records[0]["headings"][0])
    tokenizer = tiktoken.get_encoding("cl100k_base")
    records, sources = [], {}

    def add(record, text, suffix, extra=None):
        item = deepcopy(record)
        item["id"] = item["source_record_id"] = record["id"] + suffix
        item.update(text=text, document_title=title, preparation_contract="context-v2")
        if extra:
            item.update(extra)
        if len(tokenizer.encode(text)) > 950:
            raise ValueError("Prepared record exceeds native no-split limit")
        records.append(item)
        sources[item["id"]] = {**deepcopy(old_map[record["id"]]), "record_id": item["id"],
                                "parent_record_id": record["id"], "content": text}
        if extra:
            sources[item["id"]].update(extra)

    for record in old_records:
        prefix = "Paper title: " + title + "\n" + "\n".join("Section: " + h for h in record["headings"]) + "\n\n"
        if record["content_kind"] != "table":
            # Strip only the adapter's heading prefix, not source sentences.
            body = old_map[record["id"]]["content"]
            extra = None
            if record["content_kind"] == "picture":
                # OCR reading order does not encode diagram arrows or ownership.
                # Preserve labels for inspection, but do not turn their adjacency
                # into model-facing relationship evidence.
                marker = "Text extracted inside this figure (diagram labels, not prose):"
                caption, separator, labels = body.partition(marker)
                if separator:
                    body = caption.rstrip() or "[Figure has no readable caption; labels are inspection-only metadata.]"
                    extra = {"figure_labels_for_inspection": labels.strip(),
                             "figure_label_policy": "inspection_only; no inferred diagram topology"}
            budget = 900 - len(tokenizer.encode(prefix))
            tokens = tokenizer.encode(body)
            for index, start in enumerate(range(0, len(tokens), max(1, budget - 40))):
                add(record, prefix + tokenizer.decode(tokens[start:start + budget]), f":part:{index}", extra)
                if start + budget >= len(tokens):
                    break
            continue
        # Floating PDF tables can inherit the preceding prose heading in reading
        # order. Their own captions/headers are the authoritative local context.
        prefix = "Paper title: " + title + "\nContent: Results table; use its caption and row/column headers.\n\n"
        table_ref = next(r for r in record["docling_refs"] if r.startswith("#/tables/"))
        table = doc["tables"][int(table_ref.rsplit("/", 1)[1])]
        cells = table["data"]["table_cells"]
        headers = [c for c in cells if c["column_header"]]
        captions = [doc["texts"][int(c.get("cref", c.get("$ref")).rsplit("/", 1)[1])]["text"] for c in table.get("captions", [])]
        caption = "\n".join(dict.fromkeys(captions))
        section = ""
        emitted = []
        for row in range(table["data"]["num_rows"]):
            data = [c for c in cells if not c["column_header"] and c["start_row_offset_idx"] == row and c["text"].strip()]
            if not data:
                continue
            if len(data) == 1 and data[0]["col_span"] >= table["data"]["num_cols"]:
                section = data[0]["text"]
                continue
            lines = [caption, "Table row context: " + section, "Row label: " + data[0]["text"]]
            for cell in data:
                overlapping = [h for h in headers if h["start_col_offset_idx"] < cell["end_col_offset_idx"]
                               and h["end_col_offset_idx"] > cell["start_col_offset_idx"]]
                names = list(dict.fromkeys(h["text"] for h in sorted(overlapping,
                             key=lambda c: (c["start_row_offset_idx"], c["start_col_offset_idx"]))))
                label = " / ".join(names) or "Unlabelled column"
                ambiguous = cell["col_span"] > 1
                lines.append(("Unresolved merged cell; do not assign individual metrics" if ambiguous else "Cell")
                             + f" [{label}]: " + cell["text"])
            text = prefix + "\n".join(lines)
            if len(tokenizer.encode(text)) > 950:
                # Keep each cell whole with all caption/row context, never split a row mid-cell.
                base = prefix + "\n".join(lines[:3]) + "\n"
                for index, line in enumerate(lines[3:]):
                    add(record, base + line, f":row:{row}:cell:{index}", {"table_row_indices": [row]})
            else:
                add(record, text, f":row:{row}", {"table_row_indices": [row]})
            emitted.extend(c["text"] for c in data)
        # Retain table-level header/section facts even for an empty data table.
        header_text = prefix + caption + "\nColumn headings: " + "; ".join(h["text"] for h in headers)
        add(record, header_text, ":headers", {"table_row_indices": []})
        required = [c["text"] for c in cells if c["text"].strip()]
        serialized = "\n".join(r["text"] for r in records if r["id"].startswith(record["id"] + ":"))
        if any(value not in serialized for value in required):
            raise ValueError("A source table cell was omitted")
    report = {**old_report, "records": len(records), "preparation_contract": "context-v2",
              "parent_preparation": str(prepared), "document_title": title, "max_record_tokens": max(
                  len(tokenizer.encode(r["text"])) for r in records), "source_unchanged": True,
              "table_cell_content_preserved": True, "provenance_in_model_text": False,
              "figure_label_policy": "captions in model text; diagram labels retained in inspection metadata",
              "output_directory": str(output)}
    write_json(output / "input/documents.json", records)
    write_json(output / "source_map.json", sources)
    write_json(output / "preparation_report.json", report)
    write_json(output / "headings.json", read_json(prepared / "headings.json"))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("prepared", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    result = prepare_context(args.prepared, args.output)
    print({k: result[k] for k in ["records", "document_title", "max_record_tokens", "table_cell_content_preserved"]})
