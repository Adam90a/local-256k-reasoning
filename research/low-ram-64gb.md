# Strata on a 64 GB-RAM PC (simulated), 2026-11-10

Question: does the recommended setup (Qwen3.8-Flash-Next NVFP4 GPTQ on Strata, one 24 GB RTX PRO 4000) still work
on a more modest machine with 64 GB of system RAM instead of 128 GB?

**Answer: yes.** Decode drops from ~108 to ~80 tok/s and prompts take ~40% longer to read. It loads in about a minute.

## Method

The rig has 125 GiB of RAM, so a 64 GB PC is simulated with a cgroup cap rather than by pulling DIMMs:

- `scripts/run_64gb_sim.sh` stops the live Strata service, starts a second copy (`strata-64g`, :8092) under
  systemd with `MemoryMax=56G` and `MemorySwapMax=0`, benchmarks it, and starts the live service again on exit.
  56G is roughly what a 64 GB desktop leaves for the model. The cap counts the file cache too, so expert reads from
  the SSD behave as they would on a real 64 GB box.
- `configs/strata-64gb-sim.json` differs from `strata-gptq-288k.json` in five ways:
  - `--ram-budget 48` forces Strata's low-RAM mode. It would only switch on by itself below 92 GiB installed.
  - `--kv-resident` is removed, so the K/V cache lives in VRAM instead of pinned RAM.
  - `--max-context 131072`, Strata's setup default for a 24 GB card.
  - The conversation cache is turned off.
  - It uses its own expert-profile copy.
- Benchmark: `benchmarks/validation/bench_matrix.py`, the same harness as the full-RAM baseline. Each request has
  512 output tokens with thinking off, one request at a time, 2 reps per size.

What low-RAM mode did (engine log):
- 5,562 experts in the VRAM cache (14.3 GiB).
- 48.0 GiB of the remaining experts page-locked in RAM, chosen by profile rank.
- The remaining ~15 GiB of experts read from `experts.bin` on the NVMe when needed.
- The prompt chunk cut from 32K to 5.6K tokens so long prompts don't re-read the SSD on every chunk.

## Results

Run `results/64gb-sim/20261110-124745-cap56G`, compared with the full-RAM run on the same machine (2026-11-09):

| Prompt | TTFT, 64 GB | TTFT, full RAM | Decode tok/s, 64 GB | Decode tok/s, full RAM |
| --- | ---: | ---: | ---: | ---: |
| 4K | 2.7 s | 2.0 s | 80 | 110 |
| 32K | 16.2 s | 11.4 s | 82 | 108 |
| 128K | 61 s | 43.5 s | n/a* | 100 |

- Load time was ~1 minute.
- RAM peaked at the 56.0 GiB cap and never exceeded it.
- The NVMe read 161 GiB over the run (a Corsair MP600 PRO NH; the engine measured 2.5 GB/s).
- The GPU reached 89 °C on the 128K prompts.

\* The 128K prompts (131,044 tokens) nearly filled the 131,072-token window, so only 12–20 tokens were generated.
Too short to measure decode. Time to first token is valid.

## Caveats and next steps

- This is a cgroup simulation. To check the whole machine at 64 GB, boot once with the kernel parameter `mem=64G`.
- 128K decode is unmeasured. Re-run with a 120K prompt or a larger `--max-context`.
- Long outputs and thinking-on workloads were not measured.
- Upstream reports ~115 tok/s on a 64 GB PC, but with a 32 GB RTX 5090. The 24 GB card caches fewer experts in VRAM.

Reproduce: `bash scripts/run_64gb_sim.sh` (`CAP=48G` for a smaller machine, `SIZES=`/`REPS=` to change the matrix).
Run a copy of the script (`ROOT=<repo> bash /path/to/copy.sh`) if you might edit the original while it runs.
