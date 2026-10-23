Question: While adapting a model to a new task, how can training prevent it from losing previously learned knowledge?

Status: answered

Concatenating fine-tuning data with a few randomly selected pre‑training samples in each iteration avoids network forgetting, and prompt‑based continued pre‑training also helps retain original capacity when adapting LLMs to new tasks. [S1]

> Although fine-tuning boosts a model's performance, it leads to catastrophic forgetting of previously learned information. Concatenating fine-tuning data with a few randomly selected pre-training samples in every iteration avoids network forgetting [181, 152]. This is also effective in adapting LLMs for cases where fine-tuning data is small and the original capacity is to be maintained. Prompt-based continued pre-training (PCP) [182] trains the model with text and instructions related to tasks and then finally instruction-tunes the model for downstream tasks.

[S1] Pages 17; chunk `6f9b88342a6c29d8-00056`; refs: #/texts/314

Citations identify source chunks; listed pages/refs can cover more than the exact quotation.
Exact-quote checks do not independently verify a claim's meaning or factual correctness.
