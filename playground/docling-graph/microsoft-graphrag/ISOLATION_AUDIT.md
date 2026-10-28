# Why the current graph has isolated entities

24 October 2026. Completed offline investigation of `tetris-full-validated-v14`,
Tetris3D (`2610.10539v1.pdf`). **The defects are in our custom extraction contract
and model output, not missing UI edges.** No graph records were edited or restored.

## What was checked

| Check | Result |
| --- | ---: |
| Native / viewer entities | 334 / 334 |
| Native / viewer relationships | 425 / 425 |
| Missing, extra or incorrectly mapped viewer edges | 0 |
| Actual degree-zero entities | 71 |
| Saved initial/additional responses replayed | 352 / 352 |
| Canonical replay mismatches / unmatched responses | 0 / 0 |
| Evidence files fingerprinted before/after | 1,167; all unchanged |

The current `_contracts.py` and `_providers.py` hashes match the indexed run's
manifest. The original Docling JSON also matches its recorded source hash.
This diagnosis applies to the code that actually produced this graph.

All **71 isolates** were reviewed against their saved Docling-backed passages.
Their full source text, pages, original responses and rejection reasons are
recorded in `verification/isolation-audit-20261024/`. These are AI-assisted
development reviews, not independent human ground truth or an accuracy benchmark.

## 1. Citations were extracted as the wrong scientific entities

**24 isolates are author-year citations**, including the screenshot's
`ARDELEAN ET AL., 2025` and `HUANG ET AL., 2025`. Twenty-two have type Organization;
`TODOROV ET AL., 2012` has type Tool, and a combined Xia/Siddiqui citation has type
Dataset. These are not evidence that those authors constitute organizations,
tools or datasets.

Related-work paragraph `#/texts/304` (PDF 15–16) accounts for **33 of the 71
isolates**, including 22 author-year Organization nodes. Its initial response
declared 43 entities but only seven of its 17 proposed relationships survived.
No candidate relationship was generated for the screenshot's two citation nodes.
The graph renderer did not detach them.

The prompt says to extract scientific entities, but the schema accepts any
source-present name with an allowed type. It has no mechanical distinction
between an author-year citation and an organization. Conversely, **KAIST AI** on
PDF 1 is a real affiliation; an isolated affiliation does not automatically mean
a scientific relationship is missing.

Two more isolates, `TAB. 1` and `TAB. 2`, are classified as Configuration.
The structural-name guard in `_contracts.py:116` recognizes `Table` but misses
the abbreviation `Tab.`. These should remain document references.

## 2. Additional-pass validation forgets initial-pass endpoint declarations

`_contracts.py:123` resolves relationship endpoints only against the current
response's entity list. Both calls to `project(...)` in `_providers.py` validate
one response at a time. The continuation preserves the earlier JSON for the
model, but does not provide its accepted declarations to the validator.

The prompt requests only newly found records and asks the model to repeat
endpoints when necessary. That instruction is not reliably followed. Thus a
relationship can reference an already extracted entity and still be rejected.

Of 250 rejected relationship occurrences with missing endpoints, **144 are in
additional passes** and 106 in initial passes. A controlled replay using only
accepted initial declarations from the **same verified source/history pair**
makes **100 occurrences** pass the existing checks. They represent 73 undirected
pairs, of which **47 pairs are absent from the current graph**. Fourteen current
isolates participate in these candidates. These are *candidate counts*, not
100 true missing facts or a promised 47-edge improvement.

Example: Table 5's `Ours (GT)` row (PDF 22) has a missing `REPORTS CD-S` assertion
for **3.68**. Its first-cell quote is continuous, and the prior pass declared
the necessary endpoint. Thirteen other row claims concatenate the Method cell
with nonadjacent later cells, so declaring endpoints does not fix their quotes.

The offline experiment never consults unrelated chunks to invent endpoints,
accepts no rejected initial declarations, and blocks conflicting types. It has
not been connected to the active provider or written into the graph.

## 3. Some validator rules reject legitimate relationships

### Metric dependencies

`_contracts.py:138` rejects every Metric target unless the relation is REPORTS
or OTHER. This prevents legitimate **MMD USES Chamfer Distance** and **COV USES
Chamfer Distance** statements, because metrics can depend on other metrics.
The source is `#/texts/392`, PDF 21:

> ...using Chamfer Distance as the underlying distance measure.

The rule intended to prevent treating a reported metric as a model component,
but applies to more predicates than that. The same paragraph also has quotation
alignment problems, so changing the rule alone is insufficient for every edge.

### Parallel initialization clauses

`_contracts.py:144` splits evidence on `from` and checks only the final segment.
Paragraph `#/texts/313`, PDF 16, initializes normalization and query/output
projections from pretrained cross-attention, **and** key/value projections from
self-attention. The final `from` segment contains only self-attention, so the
earlier cross-attention target is rejected twice.

The correct repair must retain the distinct initialized subcomponents, rather
than assigning every weight in the attention branch to one source.

Both faults have isolated synthetic reproductions in
`tests/test_isolation_audit.py`. Those tests document current failures; they do
not claim a repaired production contract.

## 4. Quotation mismatch sometimes comes from model “cleanup” of extracted text

The saved source includes strings such as `Tetris3Doutperforms`, `useMinimumMatching`
and `graphby`. In several proposed quotations, the model inserts natural spaces
or punctuation, making the quote differ from the source. Some other rejected
quotes omit text between cells or genuinely misquote the passage.

The old contract reports only the first failure for a candidate. Resolving a
missing endpoint can therefore expose a second quote/type failure. We should
not interpret its original rejection reason as the complete diagnosis.

Future repair should use exact source spans, preserving the raw evidence and
an explicit alignment to any normalized display view. Disabling quotation checks
or globally ignoring punctuation would accept additional incorrect claims.

## 5. Recovering all candidates would restore incorrect facts

Every one of the 100 declaration-experiment candidates received AI-assisted
review against its complete prepared source:

| Development decision | Occurrences |
| --- | ---: |
| Supported against local prepared source | 45 |
| Do not restore: wrong owner, predicate/direction or citation identity | 33 |
| Hold: ambiguous table headers or predicate/quotation correction needed | 22 |

These are repeated occurrences, not independent true relationships. Support
against a prepared table row does not independently verify Docling's cells
against the original PDF. None of these candidates was promoted.

Examples of candidates that must not be automatically restored:

- Twelve `Tetris3D USES <primitive>` candidates quote **B.3 Dataset Generator
  Details**. The passage describes primitives for training-scene construction,
  not twelve proven dependencies of the inference method. Seven isolated
  primitive nodes participate in these wrong-scope candidates.
- Seventeen Tetris3D metric claims quote **Amodal3R†'s Table 2 row**. The repeated
  paper title made the root method available as an endpoint, but does not make
  it the owner of every table value.
- Seventeen more candidates use the correct Amodal3R row but encounter collapsed
  or missing metric column paths. They need original-table alignment before
  individual metric/value assignments can be trusted.
- `MLP HAS_COMPONENT vSS/vSLAT` reverses the source's relationship: the MLP
  projects conditioning features supplied to those generation models.

Exact quotation matching establishes text presence, not semantic ownership.
These examples are why the declaration experiment remains a separate audit.

## 6. Fragmented identities and incomplete endpoint extraction also matter

The graph has `SLAT` as an isolate alongside connected `STRUCTURED LATENTS
(SLAT)`. It also has disconnected long metric names alongside connected short
metric names. These are alias-resolution candidates, not authorization to merge
every similarly named entity. Metric variants and method configurations must
remain distinguishable.

**31 isolates have no rejected relationship candidate mentioning that exact
name.** Citation identities explain many of them; some are task/concept mentions
or aliases. A rejection repair cannot recover a relationship the model never
proposed.

`EEVEE` is a real tool with two rejected candidates, but neither pass declares
their `TETRIS3D` endpoint. Inheriting initial declarations therefore cannot fix
it. The rendering belongs to dataset generation and needs that subject resolved.

The source hierarchy was **present** in the model input. The dataset-generator
section and table row labels cited above are in the actual saved requests.
This is not simply a missing Docling-hierarchy problem. Some short inputs do
separate definitions from nearby formulas or ownership context; preparation can
improve that without inventing global dependencies.

## Repair priorities

1. Use accepted initial declarations during same-source additional-pass
   validation, retaining ambiguity checks and per-record provenance.
2. Enforce scientific entity identity: keep author-year citations and `Tab.`
   references as metadata; improve type instructions for training-image kinds
   and interaction categories. Retain legitimate disconnected entities.
3. Replace blanket Metric-target rejection with predicate-specific constraints;
   handle initialization clauses at the subcomponent level.
4. Preserve table-row and generator-versus-inference subject ownership. Do not
   let the repeated document title become a universal subject. Resolve ambiguous
   table headers before accepting numeric assignments.
5. Use exact evidence spans and explicit alias candidates; re-extract only the
   affected source records before a versioned native rebuild. Communities,
   reports and embeddings must then be regenerated consistently, not patched in
   the visualization.

This investigation added an offline auditor, diagnostic tests and review
artifacts. The active provider, extraction prompt, graph, UI and main website
remain unchanged. The room at port 8775 still serves the original 334/425 run.

## Reproduce

From this sandbox directory, with a new destination each time:

```powershell
.\.venv\Scripts\python.exe audit_isolates.py runs\tetris-full-validated-v14 --output verification\isolation-audit-new
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_isolation_audit.py -v
```

The auditor makes no API calls. An optional `--viewer-json` accepts a saved
`/api/graph` response for exact node/edge mapping comparison. Its own output must
remain outside the original run so the source evidence cannot be overwritten.

Artifacts from this investigation:

- `verification/isolation-audit-20261024/audit.json`: full mechanical replay,
  isolate provenance, original rejection records and SHA-256 integrity proof.
- `verification/isolation-audit-20261024/isolate_inventory.md`: all 71 isolates.
- `verification/isolation-audit-20261024/source_review.json`: all 71 source-backed
  node assessments, kept separate from graph data.
- `verification/isolation-audit-20261024/candidate_review.json`: all 100
  counterfactual candidates, decisions, quotations and exact model-input text.
- `verification/isolation-audit-20261024/test-results.txt`: diagnostic test output.
