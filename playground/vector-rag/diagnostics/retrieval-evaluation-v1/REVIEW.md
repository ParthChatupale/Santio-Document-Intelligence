**What was tested**

A real, read-only retrieval test against the existing PostgreSQL index for the 47-page survey `2307.06435v10.pdf`: 292 saved chunks, local IBM Granite R2 embeddings, 384 dimensions, and exact pgvector cosine search. The question uses the same pinned embedding model as the passages. No answer LLM, NVIDIA API, graph retrieval, PDF reconversion, or production application changes were involved. The database row count stayed at 292.

I prepared 13 answerable questions, three unsupported questions, and two source-quality probes. Questions and source-reference rules were frozen before retrieval in `frozen_reference.json`. This is an AI-prepared diagnostic on one paper, not independently verified ground truth or a representative accuracy benchmark. Source checking here uses saved Docling text/table records, not a fresh visual verification of every PDF region.

The search itself uses embedding similarity. The phrase rules below only grade the results; they are not used to retrieve or rerank passages. Table checks require selected row values together, rather than counting any chunk from the same table as a success. Multi-part questions require every selected evidence group.

**Measured results**

| Cutoff | Questions with all selected evidence available | Meaning |
|---|---:|---|
| First result | 5/13 (38.5%) | The first chunk contains all selected support. |
| First five | 10/13 (76.9%) | All selected support appears within five chunks. |
| First ten | 11/13 (84.6%) | All selected support appears within ten chunks. |

These are strict reference-passage hit rates, not answer accuracy. A valid alternative passage can be missed by the grading rules. In particular, the Chinchilla question retrieves a useful alternative at rank 1, discussed below. No score has been retroactively changed.

**Per-question evidence ranks**

Rank means the position of the selected source passage among the returned chunks. A dash means that it was not in the first ten. For questions needing two evidence groups, both ranks are shown.

| ID | Question | Evidence ranks | Selected source pages |
|---|---|---|---|
| q01 | How does ALiBi make attention prefer nearby tokens rather than distant ones? | 3 | 4 |
| q02 | While adapting a model to a new task, how can training prevent it from losing previously learned knowledge? | 1 | 17 |
| q03 | Do BLOOM and GLM-130B agree about whether ALiBi or rotary position encoding works better? | 4 | 23 |
| q04 | Why can LoRA avoid adding latency when a fine-tuned model is used for inference? | 5 | 21 |
| q05 | According to the Chinchilla discussion, how should model size change when the number of training tokens doubles? | - | 9 |
| q06 | For DeepSeek's compute-optimal training, how do batch size and learning rate change with compute, and what are their fitted equations? | 1, 1 | 10 |
| q07 | Which tokenization schemes does the survey list for breaking text into model input units? | 1 | 4 |
| q08 | How does direct preference optimization simplify alignment compared with the PPO-based RLHF pipeline? | 1 | 17 |
| q09 | In the datasets table, what is Vicuna's instruction-data source and how many samples are listed? | 9 | 28 |
| q10 | What size and collection source does the datasets table report for C4? | 3 | 28 |
| q11 | How many processing units and which GPU type does the model-configuration table list for BloombergGPT? | 1 | 25 |
| q12 | In the paper's MMLU leaderboard, which model is ranked first and what score and shot count are shown? | 2 | 33 |
| q13 | Contrast replaying old pre-training examples with PanGu-Sigma's Random Routed Experts as approaches to reducing catastrophic forgetting. | 1, - | 10, 17 |

**What worked, with actual evidence**

- Forgetting prevention: rank 1, page 17. The retrieved text describes concatenating fine-tuning data with randomly selected pre-training samples in every iteration. The question used different wording about losing earlier knowledge; the retrieved passage provides a concrete mechanism.
- BloombergGPT hardware: rank 1, page 25. The selected table fragment explicitly pairs BloombergGPT with 512 processing units and `40GA100`. This tests the association between model, column, and value, rather than whether the word BloombergGPT occurs somewhere.
- C4 dataset: rank 3, page 28. The retrieved row reports `806GB` and `Common Crawl` for C4. Nearby mC4 has a different size, so getting the correct row matters.
- MMLU leaderboard: rank 2, page 33. The retrieved table fragment pairs MMLU with GPT-4 and `86.4 (5-shot)`. This is a historical value reported by this paper, not a current leaderboard claim.
- DeepSeek scaling: rank 1, page 10. One chunk contains both the prose trend (larger batch size and smaller learning rate as compute increases) and the extracted equations with exponents 0.3271 and -0.1250. This shows useful co-location of prose and formulas; it does not independently validate all formula recognition.

**Where it fell short**

1. Vicuna's dataset row is only rank 9. The complete selected evidence says ShareGPT and 125k samples on page 28. A continuation of the row occurs at rank 7 without both requested values. Another model-configuration fragment at rank 10 contains a sample count. Therefore, a five-chunk context would miss the selected complete row. Nearby related prose is ranked higher. The test establishes ranking weakness; it does not prove one particular fix will solve it.
2. The two-method forgetting comparison finds the replay passage at rank 1, but the PanGu-Sigma Random Routed Experts passage is rank 61 in the full 292-chunk ranking. Both passages exist in the index. This is a retrieval coverage failure, not a failed database insert or a missing relationship-extraction step. Sending the first five or ten chunks to an LLM would omit the selected support for half the comparison. Increasing top-k to ten is insufficient.
3. The Chinchilla-specific passage is rank 139, but rank 1 is the paper's page-6 scaling-law summary: 'the model size and the number of training tokens should be scaled equally.' That supports the requested doubling relationship, although it does not name Chinchilla in prose (it cites [96]). This is a real limitation of our single-reference grading rule: the strict score calls it a miss despite useful alternative support. The explicit Chinchilla passage on page 9 remains poorly ranked. Both facts are retained; this case is not advertised as a clean complete failure or silently converted into a pass.

`miss_diagnostics.json` contains the complete rankings for the last two cases. Its first ten entries were checked against the original run. This follow-up did not alter the official top-ten results.

**Unsupported questions and similarity scores**

A nearest-neighbor retriever returns the closest passages even when none answers the question. These three facts are absent from this paper: a GPT-5 MMLU score, Santio's indexing evaluation, and the hosted API price of nemotron-3-embed-1b. The raw search nevertheless returned results:

| Unsupported request | First-result cosine similarity | What was returned |
|---|---:|---|
| GPT-5 MMLU score | 0.8516 | General MMLU discussion; GPT-4 leaderboard also appears later. |
| Santio retrieval accuracy | 0.8003 | General discussion of retrieval-augmented LLMs. |
| NVIDIA embedding API pricing | 0.8124 | A model-configuration/training hardware table. |

A similarity of 0.85 is not an 85% chance that the passage answers the question. An answering stage must check that the evidence actually supports the requested entity, attribute, and value, and say when it does not. No abstention or answer generation has been tested here. These probes do not show that an LLM hallucinated; no LLM was asked to answer them.

**Source-quality problems that retrieval cannot repair**

The ReLU passage is rank 1, yet the processed formula at `#/texts/136` says `max(hat{0}, x)`, while its saved original text says `ReLU(x) = max(0, x) (1)`. The rank is good; the enriched formula differs incorrectly from the original expression. The index used the `document` formula policy, so this error is in the current searchable text.

The architecture passage is also rank 1. Its generated description for `#/pictures/3` claims that each row has a corresponding decoder and encoder. The author text in the same chunk states that a causal decoder does not have an encoder. The description also asserts connections between the different architectures. Source metadata records AI attribution, but the contextualized text presented to a future answer model mixes generated and author content without resolving their contradiction. Generated descriptions should be treated as secondary, unverified material, not authoritative evidence.

There is also an existing coverage gap: `#/tables/0` has no extracted cells and is absent from searchable table content. Representing all 47 pages does not mean every fact on those pages was extracted. This question set intentionally checks evidence that exists in the indexed input; it cannot measure full-document extraction completeness.

**What the test justifies next**

The embedding/database stage is operational and can retrieve useful prose, table rows, and formula-containing passages. Reliable end-to-end answering is not yet established.

Before adding `rag.py`, choose a source policy: exclude unverified generated descriptions from primary evidence, and preserve original and enriched formulas separately so discrepancies remain visible. This can use existing chunker modes; it does not require changing the converter's source JSON. Keep this index and frozen evaluation as a baseline.

Then test retrieval improvements against the same questions: an established lexical retriever combined with vector search for exact names/table rows, reranking for relevance, and query decomposition for comparisons requiring two distinct passages. Row-preserving table chunks are another candidate because the current serialization can split a row. None of these is yet implemented or proven better by this test. A second paper and a separate held-out question set should check whether any improvement generalizes.

Only after that, add the answering stage using selected passages and page/reference citations, with explicit insufficient-evidence behavior. Evaluate supported answers and refusals separately from retrieval. Compare graph augmentation on the same questions and answer model after the vector baseline works; this test does not establish that GraphRAG is better or worse.

**Artifacts and reproduction**

- `../retrieval_cases_v1.json`: original questions and evidence rules.
- `frozen_reference.json`: expectations plus source excerpts and witness chunk IDs, written before retrieval.
- `results.json`: unchanged strict metrics and all ten returned passages for every question.
- `miss_diagnostics.json`: full-ranking diagnosis for the two selected misses.
- `../evaluate_retrieval.py`: evaluation script; source-reference rules grade results only.
- `../inspect_retrieval_misses.py`: read-only follow-up script.

From `C:\Santio`, run this with a new output folder (the evaluator deliberately refuses to overwrite an existing run):

```powershell
.\.venv\Scripts\python.exe .\playground\vector-rag\diagnostics\evaluate_retrieval.py .\playground\vector-rag\outputs\chunker-r2-reviewed\document-formulas\chunks.jsonl --output .\playground\vector-rag\diagnostics\retrieval-evaluation-v2
```

That command searches the existing index. It does not convert the PDF, insert duplicate vectors, or generate answers. Start the WSL PostgreSQL cluster first if it is stopped. No front-end changes were made for this evaluation.
