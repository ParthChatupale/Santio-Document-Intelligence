Terminal tracing: main question workers and CLI.

preview.log replays an existing real NVIDIA response; it makes no API requests and does not change historical question jobs. Live instrumentation emits requests/responses as they happen. Worker-to-terminal forwarding, credential redaction, closed/ASCII terminals, validation repair and raw planner/reranker events are covered by tests.
