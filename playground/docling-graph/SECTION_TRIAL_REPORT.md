# Manageable-section trial: measured result

16 October 2026. Selected source: the existing 47-page survey's saved
`C:\Santio\outputs\2307.06435v10.json`. No PDF conversion or main-app changes.

## Outcome in plain language

Smaller sections recover useful entities and findings. A real output-token
limit occurred in one challenge batch; splitting that batch further worked.
However, the model still omitted connections between extracted entities.
This trial is **not a completed semantic knowledge graph**.

The result is available at `http://127.0.0.1:8773/` while its local server runs.
Its banner explicitly labels the selected-section scope and missing inter-entity
relationships. The original React frontend and the original demonstration
latest-run pointer remain unchanged.

## Scope and reusable components

Three headings were selected: instruction tuning with LLM-generated datasets;
retrieval-augmented LLMs; and challenges/future directions. These comprise
35 of 417 native heading-aware chunks. The remaining source content was not
analyzed by this experiment. The entire source remains indexed and unchanged.

`run_sections.py` uses the existing native Docling hierarchical chunker, Docling
Graph `LlmBackend`, native identity-aware `deep_merge_dicts`, graph converter,
and the existing v2 source checks/viewer. It does not clone/fork Docling or build
a new PDF extractor. Prompts retain heading, original item-reference and page
context. Identity-aware merge tests ensure shared entities retain both their
relationships and evidence across section records.

## What happened, including failures

| Attempt | NVIDIA input tokens | Output tokens | Outcome |
|---|---:|---:|---|
| Instruction-tuning section | 5,374 | 1,923 | Extracted records |
| Retrieval section, first attempt | 5,996 | 13 | Title only, despite small input |
| Larger challenge batch | Usage unavailable | Usage unavailable | Client timeout at approximately 120 s |
| Remaining challenge batch | 5,342 | 1,276 | Extracted records |
| Retrieval retry, explicit concise JSON guidance | 6,109 | 2,202 | Recovered records |
| Challenge retry, output allowance 4,096 | 6,620 | 4,096 | `finish_reason=length`; truncated |
| First half of the failed challenge batch | 5,673 | 1,218 | Completed normally |
| Second half of the failed challenge batch | 5,660 | 1,241 | Completed normally |

There were **eight actual logged API calls**, not eight successful extractions.
The first run and retries obeyed their original six-call budget. The additional
smaller-batch experiment had a separate three-call ceiling and used two calls.
Successful original batches were not sent again. Combining results was offline
and made zero additional model requests.

Returned usage totals 40,774 input and 11,969 output tokens across calls with
usage. The timed-out request returned no usage, so these are incomplete totals,
not a claim that the timeout consumed zero tokens. Initial per-batch logs used
zero for absent usage; the runner now records unknown usage explicitly instead.

The output limit was real in the challenge retry: the model used exactly its
4,096 allowance and reported `length`. It was not the explanation for either
title-only response, both of which stopped normally after 13 output tokens.
The smaller challenge halves retained the same 4,096 allowance and completed
with approximately 1,200 output tokens each.

Thus, the test supports smaller extraction batches and concise output. It does
not support claiming that a single NVIDIA input/output limit caused every
earlier failure. NVIDIA's [model card](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/modelcard)
advertises a model context capability up to 1M tokens, which should not be
confused with a guarantee about a particular hosted endpoint's serving limits.
This experiment did not probe that endpoint's absolute maximum context.

## Preserved artifacts

Original four-batch attempt and bounded retries:

`outputs/2307.06435v10-sections-20261016T102451194569Z`

Further-split challenge batch:

`outputs/2307.06435v10-sections-20261016T103446858016Z`

Combined, offline-generated trial:

`outputs/2307.06435v10-sections-combined-20261016T103731468257Z`

Raw prompts/responses, validated per-batch models, attempt histories, token
usage, rejected truncation, source references, final records and graph are
retained. Truncated output was excluded from the accepted merge, rather than
being silently presented as complete. Both smaller replacement batches succeeded.
`outputs/latest_sections_trial.json` points to the combined trial, separately
from the existing `latest_v2.json`.

## What the graph actually contains

| Type | Candidate count |
|---|---:|
| Paper | 1 |
| Method | 18 |
| Dataset | 3 |
| Concept | 19 |
| Finding | 20, including 14 limitations |

Total: **61 candidate nodes and 60 edges**. The source-linked subset contains
59 nodes and 58 edges. Source-linked is not independent factual verification.

All 60 candidate edges originate at the paper: discusses a method, describes a
dataset/concept, or reports a finding/limitation. **Zero edges connect extracted
methods, datasets or concepts to each other.** The raw model responses also omit
the nested method relationship fields, so graph conversion did not delete a
richer set of links. Bigger entity counts do not solve this issue.

For example, model descriptions mention LLaMA fine-tuning, but the records omit
the explicit `Alpaca BUILT_ON LLaMA` and `Vicuna BUILT_ON LLaMA` links. The cited
WizardCoder/StarCoder dependency is also missing.

The frozen ten-case development reference is represented in 5/10 cases under
its strict matching rules; this is not an independent accuracy score. Among
the misses, RETRO appears under its expanded name, BM25 was classified as a
Concept instead of the reference's Method convention, and all three expected
model-dependency edges are absent. A forbidden retrieval-database-as-training-
dataset link was not emitted, but zero domain edges also makes that abstention
a weak quality signal. The unfulfilled relationship gate remains explicit.

## Verification and next step

Thirty-two regression/API tests passed, including batching, native merge,
evidence retention, request-budget enforcement, recovery guards and the existing
v2 source/HTTP checks. These passing engineering tests do not overturn the live
semantic misses described above. Browser verification checked the partial-scope
banner and extracted content. No live answer calls were added to this token/
extraction trial.

The next experiment should explicitly request and validate **relationships**
from the same manageable sections, independently of catalog/entity extraction.
It must distinguish prior-work mentions, backbone/fine-tuning dependencies,
training data and retrieval databases, and be tested against the frozen source
passages before expanding to the whole survey. We should not increase the
output allowance and declare the semantic problem fixed.

The section runner now defaults to approximately 900 body tokens per batch,
4,096 maximum output tokens and concise guidance, with a bounded request/time
budget. Input token estimates are approximate; returned NVIDIA counts are
authoritative. Oversize native chunks are marked instead of silently cut.

To inspect this saved trial after restarting:

```powershell
cd C:\Santio
$SectionTrial = Get-Content .\playground\docling-graph\outputs\latest_sections_trial.json -Raw | ConvertFrom-Json
.\playground\docling-graph\run-v2.ps1 -RunDirectory $SectionTrial.run_dir -Port 8773
```

No model call occurs when starting this viewer. Use a different port if another
server already occupies 8773; do not start a second copy on the same port.
