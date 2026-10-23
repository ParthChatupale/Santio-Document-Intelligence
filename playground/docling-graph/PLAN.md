# Docling Graph playground

## Goal

Generate and inspect a research knowledge graph from an existing DoclingDocument
JSON without changing Santio's application or extraction code.

## Implementation

1. Reuse the existing project environment when the published Docling Graph
   package is already installed. Keep scripts and outputs isolated in this
   directory. Offer an optional separate environment for dependency isolation;
   avoid duplicating existing dependencies unnecessarily.
2. Accept a user-selected DoclingDocument JSON path. Inspect its content and
   heading levels before running. Never re-convert the PDF in this playground.
3. Define a small Pydantic research template: paper, methods, concepts, datasets,
   experiments, findings, and metrics. Relationships come from typed template
   fields. Preserve reported wording and experimental conditions; do not split
   ambiguous numeric cells or invent missing results.
4. Invoke Docling Graph's public run_pipeline API. Use its document loader,
   structure-preserving serialization/chunking, NVIDIA-backed extraction, Pydantic validation, graph
   construction, provenance, and exports. Do not build a second extractor.
   A thin provider adapter supplies Nemotron's reasoning flag and request
   timing/usage through the library's public custom-client hook.
5. Save each run separately, including input identity, versions, configuration
   without credentials, elapsed time, graph data, extracted records, source
   provenance, and a graph viewer. Show graph construction failures explicitly.
6. Verify offline inspection first, then perform a real model-backed run and
   inspect its outputs. Provide exact setup and run commands.

## Boundaries

- Hierarchy-preserving processing only; the earlier hierarchy ablation is deferred.
- Read the existing root .env for the NVIDIA connection, without copying or
  displaying the key. A sandbox-local .env may override it.
- Generated data and any optional sandbox environment are ignored by Git. The
  default shares existing dependencies; the original document and application
  code stay unchanged.
- A successful run verifies integration, not knowledge-graph accuracy.
- Schema validity and an entity-name provenance match do not prove a semantic
  relationship. Inspect supporting quotations and original passages.
- Figures and formula regions are not automatically interpreted simply because
  their references occur in the document.

## Completion

A selected saved document produces non-empty graph nodes and relationships,
readable extracted records, source tracing, and a usable interactive graph view.
Instructions allow another saved Docling document to be processed without edits.
