# Granth evaluation report

Generated 2026-10-10 12:06 on Intel64 Family 6 Model 142 Stepping 10, GenuineIntel · 4 logical cores · no GPU. 25 questions (20 answerable, 5 unanswerable); LLM-generated questions, not yet human-reviewed. Index searched: 12 PDF(s), 13245 chunks.

Config: LLM `gemini-3.5-flash-lite`, reranker `Xenova/ms-marco-MiniLM-L-6-v2` over the top 12 RRF candidates, abstain threshold 0.002, top-6 chunks to the LLM.

## Retrieval

| Metric | Value |
|---|---|
| Recall@1 | 60.0% |
| Recall@5 | 85.0% |
| Recall@10 | 95.0% |
| MRR@10 | 0.715 |
| Recall@5 on questions from OCR'd pages (4) | 50.0% |

### Ablation (same questions, in-process, no LLM)

| Pipeline | R@1 | R@5 | R@10 | MRR@10 |
|---|---|---|---|---|
| rrf_only | 70.0% | 95.0% | 100.0% | 0.819 |
| rrf_rerank | 60.0% | 85.0% | 95.0% | 0.715 |
| dense_only | 60.0% | 90.0% | 100.0% | 0.701 |
| bm25_only | 85.0% | 100.0% | 100.0% | 0.912 |

## Generation

| Metric | Value |
|---|---|
| Citation accuracy | 100.0% (26 citations) |
| Hallucination rate (answers with ≥1 unsupported claim) | 0.0% |
| Unsupported claims / all judged claims | 0.0% (34 claims) |
| Answered (answerable questions) | 90.0% |
| False abstention (answerable) | 10.0% |
| Correct abstention (unanswerable) | 100.0% |
| Invalid citation markers stripped | 0 |

## Latency (client-measured, sequential, after one warm-up query)

| Metric | p50 | p95 |
|---|---|---|
| End-to-end (question → final event) | 2.52 s | 3.43 s |
| Time to first answer token | 2.10 s | 2.83 s |

Server-side stages:

| Stage | p50 | p95 |
|---|---|---|
| rewrite | 0 ms | 0 ms |
| embed | 13 ms | 17 ms |
| dense | 3 ms | 21 ms |
| lexical | 88 ms | 127 ms |
| fusion | 2 ms | 4 ms |
| rerank | 753 ms | 1.23 s |
| ttft | 1.19 s | 2.43 s |
| llm | 1.70 s | 2.65 s |
| e2e | 2.52 s | 3.43 s |

## Evidence-gate threshold sweep

The run used threshold 0.002. The sweep shows 0.05 gives 100% gate abstention on unanswerable questions; the only answerable question below 0.05 (a07, 0.022) was already abstained by the LLM, so end-to-end results are unchanged at 0.05 (re-checked live). The default is now 0.05.

| Threshold | Correct abstention | False abstention |
|---|---|---|
| 0.001 | 60.0% | 0.0% |
| 0.005 | 80.0% | 0.0% |
| 0.01 | 80.0% | 0.0% |
| 0.02 | 80.0% | 0.0% |
| 0.05 | 100.0% | 5.0% |
| 0.1 | 100.0% | 5.0% |
| 0.2 | 100.0% | 5.0% |
| 0.3 | 100.0% | 5.0% |
| 0.5 | 100.0% | 5.0% |

## Per question

| ID | Hit rank | Abstained | Cit. acc. | Unsupported | E2E | Question |
|---|---|---|---|---|---|---|
| a01 | 1 | False | 100.0% | 0 | 2.71 s | What components form the spacevector denoted by the symbol W in the context of the ponderomotive force equations? |
| a02 | None | True | — | — | 3.48 s | In the generalised theory of relativity, what does the contra-variant four-vector J^u represent? |
| a03 | 1 | False | 100.0% | 0 | 2.26 s | According to the Principle of Relativity, how does the length of a rod measured by an observer moving along with it compare to its length in the stationary system? |
| a04 | 1 | False | 100.0% | 0 | 2.88 s | How can vaccination be effective in treating a rabies infection after a person has already been bitten? |
| a05 | 3 | False | 100.0% | 0 | 2.00 s | What feature does the function have at the critical point where the derivative is undefined based on the one-sided limits? |
| a06 | 1 | False | 100.0% | 0 | 2.93 s | What happens to the temperature of a substance while it is undergoing a change in state or phase transition? |
| a07 | 3 | True | — | — | 2.19 s | What is the function of the sticky substance found on the bud scales of trees like the horse-chestnut? |
| a08 | 2 | False | 100.0% | 0 | 3.22 s | What is the primary focus of Leslie T. Chang's book Factory Girls: From Village to City in Changing China in relation to global inequality? |
| a09 | 1 | False | 100.0% | 0 | 2.57 s | What specific bacterium caused the post-Thanksgiving outbreak of gastroenteritis in western Florida? |
| a10 | 8 | False | 100.0% | 0 | 2.35 s | In the context of the fundamental equations for electromagnetic processes in moving bodies, what does the symbol u represent? |
| a11 | 6 | False | 100.0% | 0 | 2.69 s | According to Table 15.9, what was the share of income received by the top quintile in the United Kingdom in 1991? |
| a12 | 1 | False | 100.0% | 0 | 2.57 s | What is the memory error known as where you cannot access stored information, often referred to as the tip-of-the-tongue phenomenon? |
| a13 | 1 | False | 100.0% | 0 | 2.51 s | What does Kepler's first law state about the shape of planetary orbits and the location of the Sun? |
| a14 | 2 | False | 100.0% | 0 | 2.52 s | What are the four steps that make up the cycle of the Stirling engine described in Example 4.6? |
| a15 | 1 | False | 100.0% | 0 | 2.52 s | What is the resulting magnification when the image formed by a magnifying lens is at infinity? |
| a16 | 3 | False | 100.0% | 0 | 4.40 s | What are the four major classes of biological macromolecules? |
| a17 | 1 | False | 100.0% | 0 | 2.08 s | What is the primary conceptual difference between a definite integral and an indefinite integral? |
| a18 | 1 | False | 100.0% | 0 | 1.96 s | Is boric acid (H3BO3) a Brønsted-Lowry acid or a Lewis acid? |
| a19 | 1 | False | 100.0% | 0 | 1.95 s | What causes the leafstalk of a pie plant (rhubarb) to be so firm? |
| a20 | 1 | False | 100.0% | 0 | 2.80 s | What three categories did sociologist Pierre Bourdieu use to group cultural capital? |
| u01 | n/a | True | — | — | 1.12 s | Who won the 2022 FIFA World Cup final? |
| u02 | n/a | True | — | — | 2.71 s | What is the current market price of one Bitcoin? |
| u03 | n/a | True | — | — | 1.18 s | How do I configure an ingress controller in Kubernetes? |
| u04 | n/a | True | — | — | 3.14 s | Which actor played the lead role in the movie Inception? |
| u05 | n/a | True | — | — | 1.01 s | What are the opening hours of the Taj Mahal on Fridays? |
