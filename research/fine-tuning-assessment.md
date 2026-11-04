# Fine-Tuning Assessment (Phase 8)

**Recommendation: do not fine-tune.** No training was run; the brief says not to spend the budget "simply because training is possible", and none of the measured gaps is one that fine-tuning on this hardware would plausibly fix.

## What the measurements say needs improving

| Area | Qwen3.8-Flash-Next result | Gap vs. Opus 5.5 | Fixable by local fine-tuning? |
|---|---|---|---|
| Long-context retrieval + reasoning (262K) | 13/13 on all 3 shared prompts, 10/10 stability runs | none | n/a |
| 512K | 13/13 on 2/2 | none measured | n/a |
| Math reasoning (AIME 2026, 15) | 14/15 | −1 | not meaningfully (one problem) |
| Hard competitive coding (LCB v6, 10) | 3/10 (7 cut off at 32K tokens; 64K budget did not rescue the one retried) | −3 | unlikely: this is base capability on the hardest problems, which needs large-scale RL, not a LoRA |

The local model is already at the cloud reference on what the brief prioritizes most (reliable 256K reasoning). The remaining gap is frontier-level contest coding.

## Feasibility on this workstation (ESTIMATED)

| Method | Requirement for a 125B-param MoE (+51B n-gram) | Fits RTX PRO 4000 + 125 GB RAM? |
|---|---|---|
| Full fine-tune | ~2 TB+ of weights, gradients, optimizer state | No |
| LoRA (bf16 base) | base alone is 354 GB | No |
| QLoRA (4-bit base) | ~82 GB resident base plus activations at useful sequence lengths; MoE QLoRA needs every routed expert reachable for the backward pass, and the CPU-offload path in mainstream trainers is not built for 512-expert MoE | No: weights alone exceed VRAM by >3×, and CPU-offloaded backward passes through 48 MoE layers would run at a few tokens/s, making even a 10M-token run take weeks |
| Long-context fine-tune (256K sequences) | activation memory at 256K is far beyond 24 GB even with checkpointing | No |
| Rented GPUs (e.g. 4–8× H100 for QLoRA) | possible, but outside the brief (single RTX PRO 4000) and the expected gain is small | Out of scope |

## Better levers than fine-tuning

1. **Reasoning budget**: allow ≥64K output tokens on hard tasks (window sizing rule in `deployment/README.md`).
2. **Repository retrieval**: for codebases larger than the window, index the repo and feed relevant files rather than training on it. A repo-specific LoRA would go stale with every commit anyway.
3. **Agent harness**: Claude Code driving the local model (Phase 10) adds tool use, tests and self-correction, which helps the coding gap more directly than weights do.
4. **Faster quantization** (3-bit IQ3_S results in `quantization-study.md`): speed matters more for agentic loops than a marginal quality gain.

## If fine-tuning becomes worth revisiting

Revisit only if (a) a smaller dense long-context model of comparable quality appears (≤30B, QLoRA-able on 24 GB at short sequence lengths), or (b) Adam has a repeated, narrow task where the model fails in a consistent way (format, house style, domain terms). In that case: collect 1–5K examples of the failure, train a QLoRA on rented hardware, then evaluate with this repo's harness before and after.
