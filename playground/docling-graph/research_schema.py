"""Research-paper template for Docling Graph, not a separate extractor.

Entity names and descriptions must come from the source. Nested model fields
with edge_label metadata define relationships for Docling Graph's converter.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceExcerpt(BaseModel):
    """A supporting quotation; a quotation is not independent verification."""

    model_config = ConfigDict(is_entity=False, extra="ignore")
    quote: str = Field(description="A short verbatim passage supporting this record; never invent a quote.")


class Concept(BaseModel):
    """A named technical concept actually used or described in the paper."""

    model_config = ConfigDict(is_entity=True, graph_id_fields=["name"], extra="ignore")
    name: str = Field(description="Source-reported concept or component name, not a generic invented category.")
    description: str = Field(default="", description="Meaning in this paper; preserve qualifications.")


class Dataset(BaseModel):
    """A named dataset or benchmark. Its use is specified by experiment edges."""

    model_config = ConfigDict(is_entity=True, graph_id_fields=["name"], extra="ignore")
    name: str = Field(description="Actual named dataset or benchmark from Methods or Experiments. General phrases such as 'synthetic scenes' or a list of citations are not dataset names; omit those rather than invent a benchmark.")
    description: str = Field(default="", description="What the dataset contains, if stated.")


class Metric(BaseModel):
    """A reported evaluation metric, preserving the original abbreviation."""

    model_config = ConfigDict(is_entity=True, graph_id_fields=["name"], extra="ignore")
    name: str = Field(description="Actual named measurement from evaluation tables or metric definitions, such as accuracy or F1. Broad goals such as 'generation quality' are not metrics unless explicitly defined as one. Preserve abbreviations; do not guess expansions.")
    description: str = Field(default="", description="Definition and scale only when explicitly given.")


class Method(BaseModel):
    """A proposed method, comparison method, or named component."""

    model_config = ConfigDict(is_entity=True, graph_id_fields=["name"], extra="ignore")
    name: str = Field(description="Explicit method name. Resolve 'ours' to the paper's named method when supported.")
    role: Literal["proposed", "baseline", "component", "other", "unknown"] = "unknown"
    description: str = Field(default="", description="What the method does; distinguish author claims from established facts.")
    concepts: list[Concept] = Field(
        default_factory=list,
        description="Only concepts the source explicitly connects to this method.",
        json_schema_extra={"edge_label": "USES_CONCEPT"},
    )
    evidence: list[SourceExcerpt] = Field(default_factory=list)


class Finding(BaseModel):
    """A source-reported contribution, result, or limitation, retaining caveats."""

    model_config = ConfigDict(is_entity=True, graph_id_fields=["statement"], extra="ignore")
    statement: str = Field(description="A specific source-supported finding. Keep negation, scope, conditions, and caveats.")
    kind: Literal["contribution", "result", "limitation", "other"] = "other"
    reported_value: str | None = Field(
        default=None,
        description="Original value string only if the method/dataset/metric assignment is unambiguous. Otherwise null; never split a merged numeric cell by guessing.",
    )
    metrics: list[Metric] = Field(
        default_factory=list,
        description="Metrics explicitly associated with this finding, or empty when absent.",
        json_schema_extra={"edge_label": "MEASURED_BY"},
    )
    evidence: list[SourceExcerpt] = Field(default_factory=list)


class Experiment(BaseModel):
    """A particular evaluation setup, not a score attributed globally to a method."""

    model_config = ConfigDict(is_entity=True, graph_id_fields=["name"], extra="ignore")
    name: str = Field(description="Specific source-derived evaluation task, benchmark comparison, or ablation name from the experiments/results sections. Avoid generic placeholders such as 'comprehensive experiments'.")
    conditions: str = Field(default="", description="Task, split, inputs, and protocol explicitly stated for this experiment; acknowledge missing details.")
    methods: list[Method] = Field(
        default_factory=list,
        description="Methods explicitly evaluated in this experiment, not every method mentioned nearby.",
        json_schema_extra={"edge_label": "EVALUATES"},
    )
    evaluation_datasets: list[Dataset] = Field(
        default_factory=list,
        description="Datasets explicitly used for evaluation in this experiment; keep separate from training datasets.",
        json_schema_extra={"edge_label": "EVALUATED_ON"},
    )
    training_datasets: list[Dataset] = Field(
        default_factory=list,
        description="Datasets explicitly used to train the evaluated setup, if specified. Do not infer from a citation.",
        json_schema_extra={"edge_label": "TRAINED_ON"},
    )
    findings: list[Finding] = Field(default_factory=list, json_schema_extra={"edge_label": "REPORTS"})
    evidence: list[SourceExcerpt] = Field(default_factory=list)


class ResearchPaper(BaseModel):
    """Extract across Methods, Experiments, Results and Limitations, not just the abstract. Use named datasets and metrics. Keep contributions separate from cited prior work; omit unsupported links and retain caveats."""

    model_config = ConfigDict(is_entity=True, graph_id_fields=["title"], extra="ignore")
    title: str = Field(description="Actual title of this paper, not its filename or the title of a cited paper.")
    research_question: str = Field(default="", description="The problem this paper addresses, based on its text.")
    methods: list[Method] = Field(default_factory=list, json_schema_extra={"edge_label": "DESCRIBES_METHOD"})
    experiments: list[Experiment] = Field(default_factory=list, json_schema_extra={"edge_label": "HAS_EXPERIMENT"})
    findings: list[Finding] = Field(
        default_factory=list,
        description="Paper-level contributions and limitations; experimental results belong under their experiments.",
        json_schema_extra={"edge_label": "REPORTS"},
    )
