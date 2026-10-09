# Granth evaluation report

Generated 2026-10-09 13:31 on Intel64 Family 6 Model 142 Stepping 10, GenuineIntel · 4 logical cores · no GPU. 25 questions (20 answerable, 5 unanswerable); LLM-generated questions, not yet human-reviewed. **Index searched: biology-2e.pdf only (1 PDF, 2,237 chunks)** — a snapshot taken while the other 11 PDFs were still ingesting; background OCR/embedding shared the CPU during this run, which inflates the rerank stage.

Config: LLM `gemini-3.5-flash-lite`, reranker `Xenova/ms-marco-MiniLM-L-6-v2` over the top 12 RRF candidates, abstain threshold 0.002, top-6 chunks to the LLM.

## Retrieval

| Metric | Value |
|---|---|
| Recall@1 | 75.0% |
| Recall@5 | 90.0% |
| Recall@10 | 95.0% |
| MRR@10 | 0.821 |
| Recall@5 on questions from OCR'd pages (2) | 50.0% |

### Ablation (same questions, in-process, no LLM)

| Pipeline | R@1 | R@5 | R@10 | MRR@10 |
|---|---|---|---|---|
| rrf_only | 70.0% | 90.0% | 95.0% | 0.776 |
| rrf_rerank | 75.0% | 90.0% | 95.0% | 0.821 |
| dense_only | 60.0% | 70.0% | 90.0% | 0.680 |
| bm25_only | 75.0% | 90.0% | 95.0% | 0.817 |

## Generation

| Metric | Value |
|---|---|
| Citation accuracy | 100.0% (32 citations) |
| Hallucination rate (answers with ≥1 unsupported claim) | 0.0% |
| Unsupported claims / all judged claims | 0.0% (49 claims) |
| Answered (answerable questions) | 90.0% |
| False abstention (answerable) | 10.0% |
| Correct abstention (unanswerable) | 100.0% |
| Invalid citation markers stripped | 0 |

## Latency (client-measured, sequential, after one warm-up query)

| Metric | p50 | p95 |
|---|---|---|
| End-to-end (question → final event) | 3.44 s | 4.07 s |
| Time to first answer token | 3.38 s | 4.49 s |

Server-side stages:

| Stage | p50 | p95 |
|---|---|---|
| rewrite | 0 ms | 0 ms |
| embed | 27 ms | 50 ms |
| dense | 2 ms | 21 ms |
| lexical | 35 ms | 59 ms |
| fusion | 2 ms | 19 ms |
| rerank | 2.28 s | 2.58 s |
| ttft | 978 ms | 1.67 s |
| llm | 1.08 s | 1.96 s |
| e2e | 3.43 s | 4.06 s |

## Evidence-gate threshold sweep

| Threshold | Correct abstention | False abstention |
|---|---|---|
| 0.001 | 100.0% | 0.0% |
| 0.005 | 100.0% | 5.0% |
| 0.01 | 100.0% | 5.0% |
| 0.02 | 100.0% | 5.0% |
| 0.05 | 100.0% | 5.0% |
| 0.1 | 100.0% | 10.0% |
| 0.2 | 100.0% | 10.0% |
| 0.3 | 100.0% | 10.0% |
| 0.5 | 100.0% | 25.0% |

## Per question

| ID | Hit rank | Abstained | Cit. acc. | Unsupported | E2E | Question |
|---|---|---|---|---|---|---|
| a01 | 2 | False | 100.0% | 0 | 3.44 s | What percentage of animal species are classified as invertebrates? |
| a02 | None | False | 100.0% | 0 | 3.89 s | Into which two main groups are seed plants divided, and how do they differ regarding their seeds? |
| a03 | 1 | False | 100.0% | 0 | 3.55 s | Where does the majority of atmospheric carbon dioxide originate according to the biological carbon cycle? |
| a04 | 4 | False | 100.0% | 0 | 4.11 s | How do host cells and ingested bacteria relate to the evolutionary origins of mitochondria and chloroplasts according to the endosymbiotic theory? |
| a05 | 1 | False | 100.0% | 0 | 3.56 s | What specialized hyphae do parasitic fungi use to penetrate host tissues and absorb nutrients? |
| a06 | 1 | False | 100.0% | 0 | 3.17 s | What function does the protein keratin serve in the scaly skin of reptiles? |
| a07 | 1 | False | 100.0% | 0 | 3.41 s | What organisms perform the majority of global photosynthesis? |
| a08 | 2 | True | — | — | 3.53 s | Which specific plant parts are used to produce the spices saffron and cloves? |
| a09 | 1 | False | 100.0% | 0 | 3.24 s | What top predator of the Cambrian period was an arthropod-like creature over a meter long with compound eyes and spiky tentacles? |
| a10 | 1 | True | — | — | 3.60 s | What is the primary mechanism by which sodium ions are reabsorbed in the proximal convoluted tubule (PCT) during tubular reabsorption? |
| a11 | 1 | False | 100.0% | 0 | 3.10 s | What is demography? |
| a12 | 1 | False | 100.0% | 0 | 3.80 s | How do smaller endothermic animals' basal metabolic rates (BMR) per body weight compare to those of larger endothermic animals, and why? |
| a13 | 1 | False | 100.0% | 0 | 3.49 s | How many photons are required to fully reduce one molecule of NADP+ to NADPH during photosynthesis? |
| a14 | 6 | False | 100.0% | 0 | 3.37 s | In what form do fungi store carbohydrates, and what organic compound makes up their cell walls? |
| a15 | 1 | False | 100.0% | 0 | 3.44 s | What primary mechanism causes the interior of a resting neuron to be negatively charged relative to the outside? |
| a16 | 1 | False | 100.0% | 0 | 3.40 s | Why did Gregor Mendel need to examine large sample sizes of pea plants when applying probability laws to trait inheritance? |
| a17 | 1 | False | 100.0% | 0 | 3.51 s | How does antibody neutralization protect host cells from extracellular pathogens? |
| a18 | 1 | False | 100.0% | 0 | 8.65 s | How does dehydration affect the diffusion rate within a cell's cytoplasm and impact cellular function? |
| a19 | 1 | False | 100.0% | 0 | 3.51 s | Which bones of the human body develop through intramembranous ossification? |
| a20 | 1 | False | 100.0% | 0 | 3.63 s | Where in the human body is irregularly arranged fibrous connective tissue located, and why is it found there? |
| u01 | n/a | True | — | — | 2.20 s | Who won the 2022 FIFA World Cup final? |
| u02 | n/a | True | — | — | 2.40 s | What is the current market price of one Bitcoin? |
| u03 | n/a | True | — | — | 2.44 s | How do I configure an ingress controller in Kubernetes? |
| u04 | n/a | True | — | — | 2.29 s | Which actor played the lead role in the movie Inception? |
| u05 | n/a | True | — | — | 2.18 s | What are the opening hours of the Taj Mahal on Fridays? |
