# Survey extraction failure: investigated findings

16 October 2026. Investigation only: no original app/frontend/backend changes,
no PDF re-extraction and no replacement of the current demonstration run.

## What was actually sent

Failed run: `outputs/2307.06435v10-v2-direct-20261016T074713768464Z`.
Its input was `C:\Santio\outputs\2307.06435v10.json`, the full saved
DoclingDocument JSON. The source SHA-256 remains
`7a1c9a584fd8586a8623b6d3fbfa36808368985cccf90ad5dff75ce1b0fc0532`.

The installed Docling Graph input handler reconstructs a DoclingDocument from
that JSON. The direct extraction path calls `export_to_markdown()` and builds
system/user text messages containing that Markdown and the target schema.
It does not send PDF bytes, page images or the raw Docling JSON to NVIDIA.
References inside the saved JSON are resolved locally as document content is
serialized; they are not the only material presented to the model.

The investigation rebuilt that request using the original saved schema and
settings. Its exact request-cache fingerprint matches the saved original cache
entry. The reconstructed messages and original cached response are preserved in:

`outputs/2307.06435v10-v2-direct-20261016T074713768464Z/investigation/20261016T101219865128Z/`

The Markdown contained 349,120 characters. Its References section accounted for
101,715 characters, about 29.1% by characters. Those are not token percentages.
The full API prompt used 97,087 input tokens including instructions and schema.

## Why there was no recovery

The settings selected `many-to-one`, `extraction_contract="direct"`,
`use_chunking=True`, `structured_output=False` and `gleaning_enabled=False`.
In this actual installed implementation, direct extraction still sends the
whole document in one call. Chunking supplies provenance and does not turn that
call into per-chunk extraction.

NVIDIA returned the following raw text, ending normally after 13 output tokens:

```json
{"title": "A Comprehensive Overview of Large Language Models"}
```

There was no provider failure or output-length stop. The configured input/output
budgets were not exhausted. This is substantive under-extraction, not a transport
failure or a JSON-parser dropping a richer response.

Only `title` is required in the saved root schema. Other catalog fields default
to empty arrays, so Pydantic accepted this incomplete response. Defaulted
nonidentity fields are useful for partial/reference extraction; making every
catalog obligatorily nonempty would encourage invented facts. Completeness must
be checked separately. The sandbox now rejects a root-only graph as an
`insufficient_extraction` and does not promote it as the latest substantive run.

The library's sparse-output fallback is guarded by `self.structured_output`.
We disabled that mode with prompt JSON, so the sparse-output retry did not run.
The optional gleaning follow-up was also disabled. Therefore there was no
extraction-level recovery after the title-only response.

## Controlled diagnostic calls

Two new live NVIDIA calls used the same model, saved schema, JSON-object mode,
temperature 0, reasoning off, 8,192 maximum output tokens and bounded retries.
Both used the same 1,828-character excerpt assembled from the existing saved
heading-aware chunks for Tokenization and Attention. Original source references
are recorded alongside the excerpt. No PDF conversion was involved.

| Case | Input tokens, including instructions/schema | Response | Duration |
|---|---:|---|---:|
| Original full-document request, preserved baseline | 97,087 | Title only | 39.52 s |
| Short excerpt, unchanged native prompt | 4,754 | 3 methods and 6 concepts | 31.60 s |
| Identical short excerpt, added explicit survey-coverage instruction | 4,830 | 1 method and 8 concepts | 29.97 s |

The second live case changed only the added instruction, not its excerpt or
schema. These are diagnostic runs, not a statistically replicated benchmark.
The full-document baseline versus the short cases also changes document scope,
so it does not isolate length from every aspect of content selection.

All nine extracted entities in each short case had evidence quotations
resolvable against the original Docling source. That is source linkage, not
independent verification of the descriptions or classifications.

The unchanged prompt labelled three tokenization methods as `baseline`, although
their excerpt merely says they are commonly used schemes. That role is not
established by the cited passage. The survey-specific prompt instead represented
tokenizers as concepts and Transformer as prior work. This exposes a separate
ontology/classification issue: nonempty output and matching quotations alone do
not establish the right roles or semantic relationships.

## Conclusion supported by the evidence

The model and schema can extract information from this survey when given a
small scope, even with the original prompt. Consequently, the earlier suggestion
that an original-research template simply cannot process surveys is too strong.
Large single-pass scope is a stronger suspect in the observed under-extraction.
The model's internal reason for choosing a title-only answer cannot be proven
from these logs or two short tests.

The concrete pipeline weaknesses are established: a whole-document direct call,
no sparse recovery in the selected mode, and an initially permissive substantive
success check. The last is fixed; robust long-document extraction is not yet
implemented. Schema roles and survey relationships also need attention.

## Proposed next experiment

1. Reuse saved Docling JSON and existing native heading-aware chunks. Select
   three representative sections covering technical mechanisms, model/data
   relationships and challenges. Preserve headings, source refs and table context.
2. Freeze a small source-backed reference before extraction. Include expected
   relationships and forbidden assertions, such as calling a mentioned tokenizer
   an evaluated baseline without evidence. Reference preparation remains
   AI-assisted, not independently verified ground truth.
3. Test bounded chunk/section extraction using existing Docling Graph extraction
   and merge facilities. Start with a small explicit call/time budget, record
   partial failures and retry only empty/unresolved sections within that budget.
   Keep the original document and bibliography indexed; do not include the entire
   bibliography in every fact-extraction call.
4. Make the research ontology distinguish discussed prior work, proposed methods,
   evaluated baselines and survey taxonomies. Add only source-supported relation
   types needed by the pilot; do not fill catalog lists by requirement alone.
5. Merge through stable identities while retaining per-section records and
   evidence. Check relationship roles, source quotations and known omissions;
   only then expand to the full survey and revisit dense mode with repaired schema.

This is a recommendation, not a claim that the next extractor is already built.
It requires no new PDF extractor and no main-app/frontend changes.

## Reproduce

```powershell
cd C:\Santio
# Reconstruct and verify the original request without a model call:
.\.venv\Scripts\python.exe .\playground\docling-graph\investigate_survey_failure.py --run .\playground\docling-graph\outputs\2307.06435v10-v2-direct-20261016T074713768464Z
# Add the two bounded live excerpt calls:
.\.venv\Scripts\python.exe .\playground\docling-graph\investigate_survey_failure.py --run .\playground\docling-graph\outputs\2307.06435v10-v2-direct-20261016T074713768464Z --live
```

The diagnostic saves new artifacts only inside the selected sandbox run's
`investigation` subdirectory. Request exports exclude credentials and headers.

## Official documentation checked

- [Direct-mode provenance](https://docling-project.github.io/docling-graph/fundamentals/graph-management/provenance/)
  explicitly distinguishes a whole-document direct call from its chunk index.
- [Dense extraction](https://docling-project.github.io/docling-graph/fundamentals/extraction-process/dense-extraction/)
  describes native chunk-aware discovery/fill and coverage diagnostics. Our old
  dense failure means it still needs a bounded pilot rather than an unqualified
  recommendation to rerun the full paper.
- [Schema guidance](https://docling-project.github.io/docling-graph/fundamentals/schema-definition/)
  recommends defaulted nonidentity fields for partial extraction. Required fields
  and completeness are different concerns.
