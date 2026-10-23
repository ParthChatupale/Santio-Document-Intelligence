**Implementation result**

`rag.py` now answers questions over an existing compatible PostgreSQL vector index. Local Granite R2 embeds the question; NVIDIA Nemotron generates a structured answer from prepared retrieved passages. No PDF conversion, reindexing, graph retrieval, or frontend changes were involved.

**Checks performed**

Ten offline contract checks passed: accepted citations resolve our own pages, invented quotations/unknown IDs/model-supplied page numbers are rejected, answer-status consistency is checked, whitespace differences are handled, oversized context is refused, source snapshots are verified, unverified descriptions are removed, original formula text is selected, invalid structured output receives at most one repair, and truncated responses are not accepted. Several checks cover multiple conditions.

Real-source preparation also passed for the problematic ReLU and architecture chunks. Author text remains, generated description text is removed, and the original JSON and database text remain unchanged. See `../rag-source-policy-checks.json`.

Four live development questions produced these final statuses:

| Case | Expected and observed status | Source behavior | Report |
| --- | --- | --- | --- |
| Avoiding forgetting | answered | Cites the page-17 training passage. | [Readable output](forgetting.md), [trace](forgetting.json) |
| BloombergGPT hardware | answered | Cites the page-25 row with 512 units and 40GA100. | [Readable output](bloomberg.md), [trace](bloomberg.json) |
| GPT-5 MMLU score | insufficient_evidence | Does not substitute GPT-4's score. | [Readable output](unsupported.md), [trace](unsupported.json) |
| Two forgetting approaches | partial | Gives the supported replay explanation and identifies missing PanGu-Sigma evidence. | [Readable output](two_passages.md), [trace](two_passages.json) |

All accepted quotations passed the mechanical checks. The BloombergGPT response needed one repair because its first response contained extra text outside the JSON object. The trace retains that rejected response. Database row count was unchanged. `checks.json` records status checks, not factual-accuracy scores.

A separate terminal invocation answered the ALiBi question using a quotation from page 4. It saved both output files successfully in `../../outputs/rag-cli-reviewed/`. That exercises the user-facing command, not only direct function calls.

**Development failures were preserved**

The first two live runs are in `../rag-review-v1/` and `../rag-review-v2/`. The model sometimes refused a whole comparison despite evidence for one side, or labelled a single-method question partial because it expected an exhaustive list. The final instructions explicitly distinguish requested parts from extra requirements, and the final Nemotron requests use bounded low-effort reasoning. These changes were made during development using these same questions. This is not an independent held-out evaluation or proof that either change alone caused an improvement.

**What is still unverified**

Quote matching confirms that the quotation exists in a supplied passage; it cannot prove the claim follows logically. Manual reading of `forgetting.md` shows a remaining example: the answer adds that prompt-based continued pre-training helps retain original capacity. The cited passage explicitly attributes avoiding forgetting to replaying pre-training samples, then describes PCP separately. Extending the retention claim to PCP is broader than the explicit support. This is not counted as a factual-accuracy success merely because the status and quotation checks passed.

The source's original formulas can also be imperfect, and table extraction gaps remain. The existing vector ranking has not been improved: the full PanGu-Sigma explanation still falls outside the supplied top five. A partial answer correctly exposes that missing evidence; it does not repair the retrieval miss.

This completes a runnable baseline with inspectable evidence and failure handling. Broader human/source review, held-out answer questions, and retrieval improvements are still needed before claiming reliable end-to-end accuracy.
