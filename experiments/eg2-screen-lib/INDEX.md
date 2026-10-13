# eg2-screen-lib — run index

One line per run. TEST_HYGIENE R3 wants this generated from the `meta.json`
files rather than hand-maintained; with one run that is a grep, and it stays
honest as long as the line is derived from the file:

```sh
for m in experiments/eg2-screen-lib/meta.json; do
  python3 -c "
import json,sys; d=json.load(open('$m'))
print(d['started'][:10], d['suite'], d['label'], d['host'], d['sha'],
      '|', d['headline'], '|', d['verdict'])"
done
```

| date | suite | label | host | sha | headline | verdict |
|---|---|---|---|---|---|---|
| 2026-10-12 | eg2-screen-lib | initial-survey-and-autonomous-tutorial | 10.0.0.19 | `9bd5907` | template 1.000 vs ≤0.492 @ thr 0.75 (CPU-only); EG2 text→image cos 0.780; autonomous tutorial completed, 0 interventions | EG2 is layer 2 of a cascade, not a text embedder |
