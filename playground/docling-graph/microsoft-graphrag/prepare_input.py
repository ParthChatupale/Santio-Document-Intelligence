"""Checkpoint 1: saved Docling document -> GraphRAG text records and source map.

Run with the MAIN Python environment, which already has Docling installed.
No PDF conversion, embedding weights, credentials or model/API calls are used.
"""
import argparse
from collections import Counter
from pathlib import Path
import re

from _common import HERE, digest, stamp, write_json


def normalized(text):
    return re.sub(r"\s+", " ", text).strip()


def prepare(source, output=None, *, include_ai_descriptions=False, include_bibliography=False):
    from docling_core.types.doc import DoclingDocument
    from docling_core.types.doc.common.content_layer import ContentLayer

    source = Path(source).resolve(strict=True)
    source_hash = digest(source)
    doc = DoclingDocument.load_from_json(source)
    output = Path(output or HERE / "runs" / (source.stem + "-prepared-" + stamp())).resolve()
    if output.exists():
        raise ValueError("Output already exists. Use a new output directory; saved inputs are immutable.")
    all_items = {x.self_ref: x for x in [*doc.texts, *doc.tables, *doc.pictures]}
    owners = {}
    resolution_errors = []
    for item in [*doc.tables, *doc.pictures]:
        for ref in item.captions:
            try:
                target = ref.resolve(doc)
                if target.self_ref not in all_items:
                    raise ValueError("Caption is not a source document item")
                owners.setdefault(target.self_ref, []).append(item.self_ref)
            except (ValueError, KeyError, IndexError, AttributeError) as exc:
                resolution_errors.append({"owner": item.self_ref, "caption": ref.cref,
                                          "error": str(exc)})
    records, source_map, inventory, heading_list = [], {}, {}, []
    hierarchy = []

    def locations(item):
        return [p.model_dump(mode="json") for p in getattr(item, "prov", [])]

    def add(item, text, refs, extra=None):
        refs = list(dict.fromkeys(refs))
        ident = source_hash[:16] + ":" + item.self_ref.removeprefix("#/").replace("/", ":")
        pages = sorted({p.page_no for r in refs for p in getattr(all_items[r], "prov", [])})
        headings = [title for _, title in hierarchy]
        record = {"id": ident, "source_record_id": ident, "paper_id": source_hash,
                  "title": doc.name, "text": "\n\n".join([*("# " + h for h in headings), text]),
                  "headings": headings, "pages": pages, "docling_refs": refs,
                  "content_kind": str(item.label), "ai_description_included": False}
        if extra:
            record.update(extra)
        records.append(record)
        source_map[ident] = {"record_id": ident, "paper_id": source_hash,
                             "source_file": str(source), "item_refs": refs, "pages": pages,
                             "headings": headings, "kind": str(item.label),
                             "locations": {r: locations(all_items[r]) for r in refs},
                             "content": text, "ai_description_included": record["ai_description_included"]}
        for ref in refs:
            inventory.setdefault(ref, {"label": str(all_items[ref].label), "records": []})
            inventory[ref].update(status="included", reason="serialized_source_content")
            inventory[ref]["records"].append(ident)

    seen = set()
    for item, _ in doc.iterate_items(included_content_layers=set(ContentLayer)):
        ref = item.self_ref
        if ref not in all_items or ref in seen:
            continue
        seen.add(ref)
        label = str(item.label)
        inventory.setdefault(ref, {"label": label, "records": []})
        if label == "section_header":
            level = getattr(item, "level", 1)
            hierarchy = [(n, title) for n, title in hierarchy if n < level]
            hierarchy.append((level, item.text.strip()))
            heading_list.append({"heading": item.text, "level": level, "ref": ref})
            inventory[ref].update(status="context", reason="heading_breadcrumb", text=item.text)
            continue
        bibliography = any(re.match(r"^(?:\d+[.\s]*)?(references|bibliography)\s*$", h, re.I)
                           for _, h in hierarchy)
        if label in {"page_header", "page_footer"} or (bibliography and not include_bibliography):
            inventory[ref].update(status="excluded", reason="bibliography" if bibliography else label)
            continue
        if ref in owners:
            # Serialize captions with their figure/table, never again as unrelated prose.
            if inventory[ref].get("status") != "included":
                inventory[ref].update(status="pending_caption", reason="attached_to_owner")
            continue
        if label in {"table", "picture"}:
            captions = [c.cref for c in item.captions if c.cref in all_items]
            caption_text = "\n\n".join(all_items[c].text for c in captions)
            if label == "table":
                table = item.export_to_markdown(doc=doc)
                cell_texts = [c.text for c in item.data.table_cells if c.text.strip()]
                missing = [t for t in cell_texts if normalized(t) not in normalized(table)]
                ambiguous = [i for i, c in enumerate(item.data.table_cells)
                             if not (c.column_header or c.row_header or c.row_section)
                             and (c.col_span > 1 or len(re.findall(r"(?<![\w.])[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?![\w.])", c.text)) > 1)]
                warning = ("Table extraction warning: some data cells merge columns or multiple numbers. "
                           "Do not split those values or guess their metric/dataset assignments.") if ambiguous else ""
                add(item, "\n\n".join(x for x in [caption_text, warning, table] if x), [ref, *captions],
                    {"table_source_cells": len(cell_texts), "table_cell_render_warnings": missing,
                     "ambiguous_data_cell_indices": ambiguous})
                source_map[records[-1]["id"]]["table_cells"] = [c.model_dump(mode="json") for c in item.data.table_cells]
            else:
                desc = item.meta.description if item.meta else None
                description = getattr(desc, "text", "") if desc else ""
                text = caption_text
                # Docling can store diagram labels/OCR text as picture children.
                # Keep these attached to the figure, not as free-standing claims.
                figure_refs = []
                figure_text = []
                for child, _ in doc.iterate_items(root=item, traverse_pictures=True,
                                                included_content_layers=set(ContentLayer)):
                    child_text = getattr(child, "text", "").strip()
                    if child.self_ref != ref and child.self_ref in all_items and child.self_ref not in captions and child_text:
                        figure_refs.append(child.self_ref)
                        figure_text.append(child_text)
                if figure_text:
                    text += "\n\nText extracted inside this figure (diagram labels, not prose):\n" + "\n".join(figure_text)
                if description and include_ai_descriptions:
                    text += "\n\nAI-generated description (unverified):\n" + description
                if not text.strip():
                    inventory[ref].update(status="unresolved", reason="picture_has_no_text_caption_or_enabled_description")
                else:
                    add(item, text, [ref, *captions, *figure_refs], {"ai_description_available": bool(description),
                        "figure_text_refs": figure_refs,
                        "ai_description_included": bool(description and include_ai_descriptions)})
        else:
            text = getattr(item, "orig", "") if label == "formula" else getattr(item, "text", "")
            if not text.strip():
                inventory[ref].update(status="unresolved", reason="empty_original_formula" if label == "formula" else "empty_source_text")
                continue
            add(item, text, [ref])
    for ref, item in all_items.items():
        if ref not in inventory:
            inventory[ref] = {"label": str(item.label), "status": "unresolved", "reason": "not_in_document_traversal", "records": []}
        elif inventory[ref].get("status") == "pending_caption":
            inventory[ref].update(status="unresolved", reason="caption_owner_not_serialized")
    if not records:
        raise ValueError("No readable source records exported.")
    unresolved = [r for r, v in inventory.items() if v["status"] == "unresolved"]
    report = {"status": "prepared_with_unresolved" if unresolved or resolution_errors else "prepared",
              "source": str(source), "source_sha256": source_hash, "document_name": doc.name,
              "pages": len(doc.pages), "records": len(records), "source_items": len(all_items),
              "accounted_items": len(inventory), "statuses": dict(Counter(v["status"] for v in inventory.values())),
              "source_unchanged": digest(source) == source_hash, "resolution_errors": resolution_errors,
              "unresolved_refs": unresolved, "table_render_warnings": sum(bool(r.get("table_cell_render_warnings")) for r in records),
              "tables_with_ambiguous_data_cells": sum(bool(r.get("ambiguous_data_cell_indices")) for r in records),
              "include_ai_descriptions": include_ai_descriptions, "include_bibliography": include_bibliography,
              "model_calls": 0, "output_directory": str(output), "item_inventory": inventory}
    write_json(output / "input/documents.json", records)
    write_json(output / "source_map.json", source_map)
    write_json(output / "headings.json", heading_list)
    write_json(output / "preparation_report.json", report)
    preview = "\n\n---\n\n".join("Source record: " + r["id"] + "\nPages: " + str(r["pages"]) + "\n\n" + r["text"] for r in records)
    (output / "preview.md").write_text(preview, encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--include-ai-descriptions", action="store_true")
    parser.add_argument("--include-bibliography", action="store_true")
    args = parser.parse_args()
    report = prepare(args.source, args.output, include_ai_descriptions=args.include_ai_descriptions,
                     include_bibliography=args.include_bibliography)
    import json
    print(json.dumps({k: v for k, v in report.items() if k != "item_inventory"}, indent=2))


if __name__ == "__main__":
    main()
