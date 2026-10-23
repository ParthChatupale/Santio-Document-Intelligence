# Relationship extraction and validation fix

16 October 2026. All changes remain under the Docling Graph playground. Santio's
original React frontend and backend have not been modified.

## What changed

Previously, default-empty method relationship fields allowed an entity catalog
to validate despite omitting clearly stated dependencies. Recovery instructions
also emphasized catalogs. The saved raw responses confirmed the graph converter
was not deleting richer links.

The sandbox now uses a focused, required typed projection: model dependencies,
training datasets, method components and mechanisms, with source reviews for
every supplied item. Dependencies map to the existing `BUILT_ON` field and native
Docling Graph converter; no PDF extractor or graph library was replaced.

Every proposal needs exact, scoped source quotations, correct endpoint types,
unambiguous endpoint names and a relationship cue. Names inside longer
hyphenated model names do not establish the shorter entity. Unknown training
dataset names are withheld rather than treating generators or generic amounts
of instructions as named datasets. Retrieval databases are not silently treated
as training corpora. These conservative checks may also withhold valid links.

A separate bounded NVIDIA request checks semantic entailment and direction,
including which model owns which training data in a shared paragraph. This is
model review, not independent ground truth. Only proposals passing both stages
are projected. A positive model review cannot rescue a failed quotation check.

The knowledge-graph gate now distinguishes substantive records from actual
source-linked inter-entity relationships. Frozen examples also require the
expected source references, not merely matching edge names. Empty output never
establishes completeness. Known development checks remain enforced on offline
postprocessing. Unresolved source reviews prevent promotion as a successful trial.

## Measured final result

Saved run:

`outputs/2307.06435v10-relationships-reviewed-20261016T110733947222Z`

The original section trial supplied entities/findings from 35 of 417 chunks,
covering three selected headings. The final relationship extraction/review
covered **four chunks in the instruction-tuning heading**, not all three headings
or the whole 47-page paper. Previously extracted other-section content remains.

The final graph has **63 candidate nodes and 69 edges**. Its source-linked subset
has **61 nodes and 67 edges**. Most edges still link the paper to its contents;
the meaningful change is **seven method-to-method/dataset connections**, previously
zero in the baseline section trial:

| Subject | Relationship | Object | PDF page |
|---|---|---|---|
| Alpaca | BUILT_ON | LLaMA | 16 |
| Vicuna | BUILT_ON | LLaMA | 16 |
| LLaMA-GPT-4 | BUILT_ON | LLaMA | 16 |
| Goat | BUILT_ON | LLaMA | 16 |
| WizardLM | BUILT_ON | LLaMA | 16 |
| WizardCoder | BUILT_ON | StarCoder | 16 |
| Vicuna | TRAINED_ON | ShareGPT.com | 16 |

**Four of four targeted positive development checks pass**, with the expected
source references. The forbidden Alpaca-to-ShareGPT training link is absent.
This is a development regression result, not an accuracy percentage or proof of
exhaustive recall. The original three dependency examples were frozen before
the trials. The added training-ownership regressions were prepared after an
observed failure, before the semantic-review request, and are labeled accordingly.

Ten proposals were considered in the final extraction; seven survived and three
were withheld:

- Alpaca TRAINED_ON ShareGPT.com: the semantic review correctly identifies that
  the source assigns those samples to Vicuna, not Alpaca.
- WizardLM TRAINED_ON SUPER-NATURALINSTRUCTIONS: both quotation checks and review
  reject this unsupported assignment.
- HuaTuo BUILT_ON LLaMA: insufficient explicit endpoint support in its quoted
  evidence. The model reviewer accepted a contextual implication, but deterministic
  checks still withheld it. This disagreement illustrates why review alone is
  insufficient and why the result is not called verified ground truth.

The seven retained connections were additionally inspected against the saved
source by the coding assistant. That inspection is AI-assisted, not independent
human annotation. Figures, equations and unreviewed sections remain outside this
relationship experiment.

## Attempts and API accounting

The work made **11 actual extraction/review requests** across separately bounded
experiments: six flat-projection calls, three initial typed-projection calls,
one improved quotation-context extraction, and one semantic-review call.
No original PDF was sent or re-extracted. Original source hashes are unchanged.
Each experiment preserved its prompts, responses, proposal checks and call usage.

The flat projection still confused relation labels and endpoint types. The first
typed projection recovered dependencies but produced incomplete supporting
quotations. A boundary check also exposed matches to a shorter model name inside
a longer name. These intermediate artifacts are diagnostic history, not approved
graphs. The final quotation pass returned ten proposals in 57.58 seconds, with
3,161 input and 2,105 output tokens. The separate semantic review took 11.66
seconds. The final run's `model_calls.json` records these two phases; it does not
include the nine earlier experiment requests.

The first final extraction could attach the wrong dataset despite matching
names and a training keyword in a full paragraph. This was the direct reason to
add semantic review rather than claiming quotation matching proved correctness.

## Verification and display

- **49 regression/API tests passed**, including wrong-clause rejection, incomplete
  reviews, invented quotations, wrong references, endpoint types, training versus
  retrieval, name boundaries, native conversion and evidence preservation.
- Local HTTP overview, graph, evidence, retrieval and viewer endpoints return 200;
  the PDF range request returns 206 with valid PDF bytes.
- Retrieval returns the actual Alpaca BUILT_ON LLaMA edge with its source passage.
- Browser verification confirms seven relationship cards, their quotations, the
  graph, and a working source link to PDF page 16.
- The original frontend/backend paths show no changes. Saved result text files
  were scanned for the configured API secret; none contained it.

Open `http://127.0.0.1:8774/` while the separate sandbox server runs and select
**Relationships**. The interface labels the partial scope and exposes matching
source quotations. Reopening the saved result makes no model requests.

Next coverage work should apply this pipeline to more sections, then measure
missing and unsupported links against a larger independent reference. Current
success does not establish that all relationships in this paper were recovered.
