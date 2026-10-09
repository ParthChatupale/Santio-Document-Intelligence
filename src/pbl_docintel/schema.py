"""Strict contracts; structural validity does not establish factual correctness."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import SCHEMA_VERSION

Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Nonempty = Annotated[str, Field(min_length=1)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class BoundingBox(Contract):
    l: float
    t: float
    r: float
    b: float
    coord_origin: Literal["TOPLEFT", "BOTTOMLEFT"]


class Location(Contract):
    page_no: Annotated[int, Field(ge=1)]
    bbox: BoundingBox | None = None
    granularity: Literal["item", "cell", "table"] = "item"
    charspan: list[int] | None = None


class Cell(Contract):
    index: Annotated[int, Field(ge=0)]
    row_start: Annotated[int, Field(ge=0)]
    row_end: Annotated[int, Field(ge=1)]
    col_start: Annotated[int, Field(ge=0)]
    col_end: Annotated[int, Field(ge=1)]
    column_header: bool = False
    row_header: bool = False
    row_section: bool = False

    @model_validator(mode="after")
    def positive_spans(self):
        if self.row_end <= self.row_start or self.col_end <= self.col_start:
            raise ValueError("Cell spans must be positive, with exclusive end offsets")
        return self


class EvidenceUnit(Contract):
    evidence_id: Nonempty
    item_ref: Nonempty
    kind: Literal["text", "table", "table_cell", "picture"]
    label: str
    text: str
    locations: list[Location]
    cell: Cell | None = None
    # These are structural associations, not verified semantic relationships.
    context: dict[str, list[str]] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)


class DocumentIdentity(Contract):
    document_id: Hash  # Conversion/export fingerprint; byte hash for Docling.
    docling_json_filename: Nonempty | None = None
    source_filename: Nonempty
    source_sha256: Hash | None = None
    docling_schema_version: str | None = None
    producer: Nonempty = "docling"
    pages: dict[str, dict[str, float]]


class EvidenceIndex(Contract):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    document: DocumentIdentity
    units: dict[str, EvidenceUnit]

    @model_validator(mode="after")
    def consistent_evidence(self):
        for key, unit in self.units.items():
            if key != unit.evidence_id:
                raise ValueError("Evidence dictionary keys must match evidence IDs")
            if (unit.kind == "table_cell") != (unit.cell is not None):
                raise ValueError("Only table-cell units must have cell coordinates")
            if unit.kind == "table_cell":
                parent = self.units.get(unit.item_ref)
                if parent is None or parent.kind != "table":
                    raise ValueError("Table cells require a table parent in the index")
            for refs in unit.context.values():
                if any(ref not in self.units for ref in refs):
                    raise ValueError("Evidence context contains unresolved references")
            if any(str(loc.page_no) not in self.document.pages for loc in unit.locations):
                raise ValueError("Evidence location refers to an unknown page")
        return self


class EvidenceLink(Contract):
    evidence_id: Nonempty
    quote: Nonempty | None = None  # Exact substring of this unit's text.


class Name(Contract):
    reported: Nonempty
    normalized: str | None = None


class Benchmark(Contract):
    dataset: Name
    task: str | None = None
    split: str | None = None
    subset: str | None = None
    evidence: list[EvidenceLink] = Field(min_length=1)


class Metric(Contract):
    name: Name
    direction: Literal["higher", "lower", "unknown"] = "unknown"
    unit: str | None = None
    reported_scale: str | None = None
    definition_evidence: list[EvidenceLink] = Field(default_factory=list)


class ReportedValue(Contract):
    raw: Nonempty
    numeric: float | None = None
    uncertainty: str | None = None


class Condition(Contract):
    key: Nonempty
    value: Nonempty
    basis: Literal["reported", "manual_interpretation"]
    evidence: list[EvidenceLink] = Field(min_length=1)


class Review(Contract):
    status: Literal["unreviewed", "needs_review", "human_reviewed"] = "unreviewed"
    reviewer: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def require_reviewer(self):
        if self.status == "human_reviewed" and not self.reviewer:
            raise ValueError("Human review requires a reviewer identity")
        return self


class ResultRecord(Contract):
    result_id: Nonempty
    document_id: Hash
    method: Name
    variant: str | None = None
    role: Literal["main", "baseline", "ablation", "unknown"] = "unknown"
    benchmark: Benchmark
    metric: Metric
    value: ReportedValue
    value_evidence: EvidenceLink
    method_evidence: EvidenceLink
    metric_evidence: list[EvidenceLink] = Field(min_length=1)
    conditions: list[Condition] = Field(default_factory=list)
    review: Review = Field(default_factory=Review)
    notes: list[str] = Field(default_factory=list)


class ExtractionRun(Contract):
    extractor: Nonempty
    model: str | None = None
    created_at: datetime
    configuration: dict[str, str] = Field(default_factory=dict)


class ResultCollection(Contract):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    document_id: Hash
    run: ExtractionRun
    records: list[ResultRecord]

    @model_validator(mode="after")
    def consistent_records(self):
        ids = [r.result_id for r in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("Result IDs must be unique")
        if any(r.document_id != self.document_id for r in self.records):
            raise ValueError("All records must refer to the collection's conversion")
        return self
