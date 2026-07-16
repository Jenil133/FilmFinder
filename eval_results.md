# Retrieval eval (regression harness — see qa_eval.py header for methodology)

**Scored queries: 12** · hit@1 12/12 · hit@6 12/12 · MRR 1.00

| query | category | first hit rank | top-1 at |
|---|---|---|---|
| corner kick | canonical | 1 | 1:16:04 |
| goalkeeper save | canonical | 1 | 1:22:40 |
| shot on goal | canonical | 1 | 1:14:12 |
| throw-in | canonical | 1 | 1:32:26 |
| goal celebration | canonical | 1 | 1:24:30 |
| free kick | canonical | 1 | 1:20:30 |
| goals in the second half | time-filter | 1 | 1:10:14 |
| saves in the first half | time-filter | 1 | 37:30 |
| shots in the last 10 minutes | time-filter | 1 | 1:37:20 |
| players arguing with the referee | long-tail | 1 | 38:20 |
| when did the keeper mess up | long-tail | 1 | 1:27:04 |
| shots in the last 10 minutes of the first half | compound-time | 1 | 45:14 |
| counterattack after losing the ball *(expected miss — documented limitation)* | sequence | — | 1:29:44 |
