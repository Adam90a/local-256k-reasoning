# Licensing and third-party content

- **Code** (`benchmarks/`, `scripts/`, `configs/`, `deployment/`): MIT, see `LICENSE`.
- **Report, research notes and our measurements** (`research/`, `results/processed/`, run metadata and scores in `results/raw/`): CC BY 4.0.
- **Long-context test prompts** (`results/prompts/`) and the answer excerpts stored in `results/raw/` contain verbatim excerpts of third-party source code used as haystack text:
  - [llama.cpp](https://github.com/ggml-org/llama.cpp), MIT License, Copyright (c) 2023-2026 The ggml authors
  - [vLLM](https://github.com/vllm-project/vllm), Apache License 2.0, Copyright the vLLM contributors (includes vendored components under their own licenses, e.g. CUTLASS, BSD-3-Clause)
  These excerpts remain under their original licenses and are included unmodified, apart from the planted test lines, solely as benchmark input.
- `configs/qwen38fn-chat-template.*.jinja` is derived from the Qwen3.8-Flash-Next chat template (Qwen community license 1.0).
- Benchmarks referenced but not redistributed: AIME 2026 (MathArena), LiveCodeBench v6.
