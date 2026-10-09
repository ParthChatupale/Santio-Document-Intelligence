"""Overlay saved Docling detections on the original PDF without reconversion.

Requires pypdf and reportlab. The source PDF remains unchanged.
"""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor, Color
from reportlab.pdfgen import canvas


PALETTE = {
    "picture": ("Figure / picture", "#059669", "P"),
    "formula": ("Formula region", "#db2777", "F"),
    "table": ("Table", "#ea580c", "T"),
    "section_header": ("Heading", "#7c3aed", "H"),
    "text": ("Text", "#2563eb", "X"),
    "caption": ("Caption", "#0891b2", "C"),
    "list_item": ("List item", "#475569", "L"),
    "code": ("Code", "#a16207", "K"),
    "footnote": ("Footnote", "#64748b", "N"),
    "page_header": ("Page header", "#94a3b8", "A"),
    "page_footer": ("Page footer", "#94a3b8", "Z"),
}
SIDEBAR = 144


def draw_sidebar(layer, width, height, page_no, total_pages, counts, formula_enriched):
    x = width + 12
    layer.setFillColor(HexColor("#f8fafc"))
    layer.rect(width, 0, SIDEBAR, height, fill=1, stroke=0)
    layer.setStrokeColor(HexColor("#cbd5e1"))
    layer.setLineWidth(0.6)
    layer.line(width, 0, width, height)
    layer.setFillColor(HexColor("#0f172a"))
    layer.setFont("Helvetica-Bold", 13)
    layer.drawString(x, height - 34, "DOCLING")
    layer.setFont("Helvetica", 10)
    layer.drawString(x, height - 49, "Layout detections")
    layer.setFillColor(HexColor("#475569"))
    layer.setFont("Helvetica", 8)
    layer.drawString(x, height - 68, f"Page {page_no} / {total_pages}")
    layer.setFont("Helvetica-Bold", 8)
    layer.drawString(x, height - 93, "COLOR KEY / THIS PAGE")
    y = height - 111
    for label, (name, color, prefix) in PALETTE.items():
        layer.setFillColor(HexColor(color))
        layer.roundRect(x, y - 2, 8, 8, 1, fill=1, stroke=0)
        layer.setFont("Helvetica", 7.5)
        layer.setFillColor(HexColor("#334155"))
        layer.drawString(x + 14, y, name)
        layer.drawRightString(width + SIDEBAR - 12, y, str(counts[label]))
        y -= 18
    y -= 20
    layer.setFont("Helvetica-Bold", 8)
    layer.drawString(x, y, "HOW TO READ")
    layer.setFont("Helvetica", 7.3)
    formula_note = "LaTeX enrichment enabled." if formula_enriched else "LaTeX enrichment was disabled."
    for line in ["Boxes mark saved detections.", "Tags are stable within this", "export: P = picture, F = formula,", "T = table, H = heading.", "", "A picture may be a diagram,", "chart, photo, or composite.", "", "Formula regions are detected;", formula_note, "", "These are model predictions,", "not a manually corrected map.", "Check table cells before using", "them as numeric evidence."]:
        y -= 12
        layer.drawString(x, y, line)
    layer.setFillColor(HexColor("#64748b"))
    layer.setFont("Helvetica", 7)
    layer.drawString(x, 26, "Original page + saved boxes")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("document_json", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = args.pdf.resolve(strict=True)
    json_path = args.document_json.resolve(strict=True)
    output = args.output or json_path.with_name(source.stem + ".layout.pdf")
    output = output.resolve()
    if output in {source, json_path}:
        raise ValueError("The visual export must have a separate output path.")
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    summary_path = json_path.with_name(json_path.stem + ".summary.json")
    summary = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("source_sha256") != sha256(source.read_bytes()).hexdigest():
            raise ValueError("Source PDF does not match the converted document.")
    reader = PdfReader(source)
    if len(reader.pages) != len(doc["pages"]):
        raise ValueError("Source PDF and Docling document page counts differ.")
    by_page = defaultdict(list)
    label_counts = Counter()
    detections = []
    for item in [*doc["texts"], *doc["tables"], *doc["pictures"]]:
        label = item["label"]
        label_counts[label] += 1
        name, color, prefix = PALETTE.get(label, (label, "#64748b", "U"))
        tag = f"{prefix}{label_counts[label]:03d}"
        for prov in item.get("prov", []):
            entry = {"id": tag, "label": label, "ref": item["self_ref"],
                     "page": prov["page_no"], "bbox": prov["bbox"],
                     "color": color, "name": name}
            detections.append(entry)
            by_page[prov["page_no"]].append(entry)

    writer = PdfWriter()
    for page_no, original in enumerate(reader.pages, start=1):
        original.transfer_rotation_to_content()
        width, height = float(original.mediabox.width), float(original.mediabox.height)
        expected = doc["pages"][str(page_no)]["size"]
        if abs(expected["width"] - width) > 1 or abs(expected["height"] - height) > 1:
            raise ValueError(f"Page {page_no} coordinate dimensions differ from source PDF.")
        buffer = BytesIO()
        layer = canvas.Canvas(buffer, pagesize=(width + SIDEBAR, height))
        for item in sorted(by_page[page_no], key=lambda d: d["label"] in {"formula", "picture", "table"}):
            bbox = item["bbox"]
            left, right = min(bbox["l"], bbox["r"]), max(bbox["l"], bbox["r"])
            if bbox["coord_origin"] == "BOTTOMLEFT":
                bottom, top = min(bbox["b"], bbox["t"]), max(bbox["b"], bbox["t"])
            elif bbox["coord_origin"] == "TOPLEFT":
                bottom, top = height - max(bbox["b"], bbox["t"]), height - min(bbox["b"], bbox["t"])
            else:
                raise ValueError(f"Unknown coordinate origin: {bbox['coord_origin']}")
            if not (-1 <= left <= right <= width + 1 and -1 <= bottom <= top <= height + 1):
                raise ValueError(f"Detection {item['id']} exceeds page {page_no}.")
            color = HexColor(item["color"])
            layer.setStrokeColor(color)
            layer.setFillColor(Color(color.red, color.green, color.blue, alpha=0.05))
            layer.setLineWidth(0.8 if item["label"] in {"picture", "formula", "table"} else 0.45)
            layer.rect(left, bottom, right - left, top - bottom, stroke=1, fill=1)
            text = item["id"]
            layer.setFont("Helvetica-Bold", 5.2)
            text_width = layer.stringWidth(text, "Helvetica-Bold", 5.2) + 5
            label_x = max(left - text_width - 1, 0)
            label_y = min(max(top - 7.2, 0), height - 8)
            layer.setFillColor(color)
            layer.rect(label_x, label_y, text_width, 7.2, fill=1, stroke=0)
            layer.setFillColor(HexColor("#ffffff"))
            layer.drawString(label_x + 2.5, label_y + 1.5, text)
        counts = Counter(item["label"] for item in by_page[page_no])
        draw_sidebar(layer, width, height, page_no, len(reader.pages), counts,
                     summary.get("options", {}).get("formula_enrichment", False))
        layer.showPage()
        layer.save()
        page = writer.add_blank_page(width=width + SIDEBAR, height=height)
        page.merge_page(original)
        page.merge_page(PdfReader(BytesIO(buffer.getvalue())).pages[0])
    writer.add_metadata({"/Title": f"{source.stem} - Docling layout detections", "/Subject": "Detected text, figures, formulas, tables and page layout", "/Creator": "Docling detections with pypdf/reportlab visual overlay"})
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as stream:
        writer.write(stream)
    reopened = PdfReader(output)
    assert len(reopened.pages) == len(reader.pages)
    manifest = {"source_pdf": str(source), "docling_document": str(json_path),
                "output_pdf": str(output), "pages": len(reopened.pages),
                "label_counts": dict(label_counts), "detections": detections,
                "formula_enrichment": summary.get("options", {}).get("formula_enrichment", False),
                "note": "Figure/picture detection does not classify diagram types. See formula_enrichment for the conversion setting."}
    output.with_suffix(".json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved {output}")
    print(f"Pages: {len(reopened.pages)}; boxes: {len(detections)}")


if __name__ == "__main__":
    main()
