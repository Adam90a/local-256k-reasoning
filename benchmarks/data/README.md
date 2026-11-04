# Benchmark data (not included — download it)

```bash
hf download --repo-type dataset MathArena/aime_2026 data/train-00000-of-00001.parquet --local-dir aime2026
python -c "import pyarrow.parquet as pq, json; json.dump(pq.read_table('aime2026/data/train-00000-of-00001.parquet').to_pylist(), open('aime2026/aime2026.json','w'))"
hf download --repo-type dataset livecodebench/code_generation_lite test6.jsonl --local-dir lcb
```
