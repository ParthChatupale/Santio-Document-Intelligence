"""Adapters over saved Docling data and the project's existing evidence index."""
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from pbl_docintel.evidence import build_index


def normalized(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value)).casefold()).strip()


def metric_name(value):
    value = re.sub(r"^(?:(?:reconstruction|generation) quality|physical stability)\s*[-:]\s*", "", value, flags=re.I)
    return re.sub(r"[↑↓†‡]", "", value).strip()


class SourceIndex:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.raw = self.path.read_bytes()
        self.document = json.loads(self.raw.decode("utf-8-sig"))
        self.index = build_index(self.path)
        self.units = self.index.units
        self.document_id = hashlib.sha256(self.raw).hexdigest()

    def locate(self, quote, source_ref=""):
        """Exact normalized support locations; does not claim entailment."""
        needle = normalized(quote)
        if len(needle) < 12:
            if len(needle)>=2 and source_ref in self.units and needle==normalized(self.units[source_ref].text):
                return [self.anchor(source_ref)]
            return []
        candidates = [self.units[source_ref]] if source_ref in self.units else list(self.units.values())
        return [self.anchor(u.evidence_id) for u in candidates if needle in normalized(u.text)]

    def anchor(self, ref):
        unit = self.units[ref]
        return {"ref": ref, "text": unit.text, "locations": [x.model_dump(mode="json") for x in unit.locations], "issues": unit.issues}

    def table_label(self, unit):
        caption = " ".join(self.units[x].text for x in unit.context.get("captions", []))
        match = re.search(r"\btable\s+(\d+)\b", caption, re.I)
        return f"Table {match[1]}" if match else unit.item_ref

    def chunks(self):
        """Use the library's real hierarchical chunker; no PDF reconversion."""
        from docling_core.transforms.chunker.hierarchical_chunker import HierarchicalChunker
        from docling_core.types.doc import DoclingDocument
        doc = DoclingDocument.model_validate(self.document)
        chunker = HierarchicalChunker()
        result = []
        for chunk in chunker.chunk(dl_doc=doc):
            refs = [x.self_ref for x in chunk.meta.doc_items if x.self_ref in self.units]
            content = chunker.contextualize(chunk=chunk)
            pages = sorted({loc.page_no for ref in refs for loc in self.units[ref].locations})
            # Bound long narrative chunks while retaining heading and source metadata.
            for start in range(0, len(content), 6000):
                text = content[start:start + 6000]
                result.append({"id": hashlib.sha256(f"{self.document_id}:{refs}:{start}".encode()).hexdigest()[:24],
                               "text": text, "refs": refs, "headings": list(chunk.meta.headings or []), "pages": pages})
        return result

    def inventory(self, chunks):
        formulas = [x for x in self.units.values() if x.label == "formula"]
        return {"document_id": self.document_id, "source": str(self.path), "pages": len(self.document.get("pages", {})),
                "chunks": len(chunks), "headings": sum(x.label == "section_header" for x in self.units.values()),
                "formula_regions": len(formulas), "empty_formulas": sum(not x.text.strip() for x in formulas),
                "table_warnings": [{"ref": x.evidence_id, "issues": x.issues, "text": x.text} for x in self.units.values() if x.kind == "table_cell" and x.issues],
                "figure_interpretation": "not performed; text/captions only"}

    def write(self, folder, chunks):
        folder = Path(folder)
        data = {"document": self.index.document.model_dump(mode="json"), "units": {k: v.model_dump(mode="json") for k,v in self.units.items()}}
        for name, value in [("source_index.json", data), ("chunks.json", chunks), ("source_quality.json", self.inventory(chunks))]:
            (folder/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
